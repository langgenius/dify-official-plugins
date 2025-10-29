from __future__ import annotations

from io import BytesIO
from typing import Any

import numpy as np
import pydicom
from PIL import Image
from dify_plugin import Tool


class DicomMultiframeTool(Tool):
    """
    Inspect multi-frame DICOMs: report number of frames and preview a given frame.
    """

    def _invoke(self, tool_parameters: dict[str, Any]):
        file_obj = tool_parameters.get("dicom_file")
        if not file_obj:
            yield self.create_text_message("`dicom_file` is required.")
            return

        with_shapes = self._as_bool(tool_parameters.get("include_shapes"), False)
        frame_index = self._as_int(tool_parameters.get("frame_index"), 0)
        include_preview = self._as_bool(tool_parameters.get("include_preview_image"), True)
        max_edge = self._as_int(tool_parameters.get("max_preview_edge"), 256)

        blob = getattr(file_obj, "blob", None)
        if blob is None:
            yield self.create_text_message("Unable to read the uploaded file.")
            return

        filename = getattr(file_obj, "filename", "dicom_file.dcm")
        try:
            ds = pydicom.dcmread(BytesIO(blob), stop_before_pixels=False, force=True)
        except Exception as exc:  # pylint: disable=broad-except
            yield self.create_text_message(f"Failed to parse DICOM: {exc}")
            return

        try:
            arr = np.asarray(ds.pixel_array)
        except Exception as exc:  # pylint: disable=broad-except
            yield self.create_json_message({
                "number_of_frames": int(getattr(ds, "NumberOfFrames", 1) or 1),
                "error": f"No pixel array: {exc}",
            })
            return

        info: dict[str, Any] = {
            "number_of_frames": int(getattr(ds, "NumberOfFrames", 1) or 1),
        }

        if with_shapes:
            info["array_shape"] = tuple(int(x) for x in arr.shape)

        if include_preview:
            preview = self._preview_frame(arr, ds, frame_index, max_edge, filename)
            if "blob" in preview:
                blob = preview.pop("blob")
                yield self.create_blob_message(blob=blob, meta={
                    "mime_type": preview.get("mime_type", "image/png"),
                    "filename": preview.get("filename", "preview.png"),
                })
            info["preview"] = preview

        yield self.create_json_message(info)

    def _preview_frame(self, arr: np.ndarray, ds, frame_index: int, max_edge: int, original_filename: str) -> dict[str, Any]:
        frame, idx = self._select_frame(arr, ds, frame_index)
        frame = np.squeeze(frame)
        mode = "L"
        if frame.ndim == 3:
            if frame.shape[0] in (3, 4) and frame.shape[-1] not in (3, 4):
                frame = np.moveaxis(frame, 0, -1)
            if frame.shape[-1] == 3:
                mode = "RGB"
            elif frame.shape[-1] == 4:
                mode = "RGBA"
            else:
                frame = frame[..., 0]
                mode = "L"
        img8 = self._normalize_to_uint8(frame)
        image = Image.fromarray(img8, mode=mode)
        resampling = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
        MAX_BLOB_BYTES = 8 * 1024 * 1024
        current_edge = int(max_edge)
        blob = None
        pw = ph = None
        while current_edge >= 32:
            img = image.copy()
            img.thumbnail((current_edge, current_edge), resampling)
            b = BytesIO()
            try:
                img.save(b, format="PNG", optimize=True)
            except Exception:
                img.save(b, format="PNG")
            d = b.getvalue()
            if len(d) <= MAX_BLOB_BYTES or current_edge == 32:
                blob = d
                pw, ph = img.width, img.height
                break
            current_edge = max(32, int(current_edge * 0.75))
        name = (original_filename.rsplit(".", 1)[0] or "dicom") + f"_frame_{idx}.png"
        return {
            "frame_index": int(idx),
            "preview_width": int(pw or image.width),
            "preview_height": int(ph or image.height),
            "mime_type": "image/png",
            "filename": name,
            "blob": blob or b"",
        }

    def _select_frame(self, arr: np.ndarray, ds, desired: int):
        num_frames = int(getattr(ds, "NumberOfFrames", 1) or 1)
        if arr.ndim >= 4:
            frames = arr.shape[0]
            idx = max(0, min(int(desired), frames - 1))
            return arr[idx], idx
        if arr.ndim == 3 and num_frames > 1 and arr.shape[0] == num_frames:
            frames = arr.shape[0]
            idx = max(0, min(int(desired), frames - 1))
            return arr[idx], idx
        return arr, 0

    def _normalize_to_uint8(self, array: np.ndarray) -> np.ndarray:
        if array.dtype == np.uint8:
            return array
        data = array.astype(np.float32)
        vmin = float(np.min(data))
        vmax = float(np.max(data))
        if vmax == vmin:
            return np.zeros_like(data, dtype=np.uint8)
        data = (data - vmin) / (vmax - min(vmax, vmin) if vmax != vmin else 1)
        data = (data - np.min(data)) / (np.max(data) - np.min(data) + 1e-12)
        return np.clip(data * 255.0, 0, 255).astype(np.uint8)

    def _as_bool(self, value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return default

    def _as_int(self, value: Any, default: int = 0) -> int:
        if value is None:
            return default
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default
