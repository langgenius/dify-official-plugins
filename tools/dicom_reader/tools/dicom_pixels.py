from __future__ import annotations

from io import BytesIO
from typing import Any

import numpy as np
import pydicom
from PIL import Image
from dify_plugin import Tool


class DicomPixelsTool(Tool):
    """
    Extract pixel array summary and an optional preview image from a DICOM file.
    Safely returns shape/dtype and basic stats; does not dump full arrays.
    """

    PREVIEW_MIN_EDGE = 32
    PREVIEW_MAX_EDGE = 1024

    def _invoke(self, tool_parameters: dict[str, Any]):
        file_obj = tool_parameters.get("dicom_file")
        if not file_obj:
            yield self.create_text_message("`dicom_file` is required.")
            return

        include_preview = self._as_bool(tool_parameters.get("include_preview_image"), False)
        preview_frame = self._as_int(tool_parameters.get("preview_frame_index"), 0)
        max_preview_edge = self._as_int(tool_parameters.get("max_preview_edge"), 256)

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
            yield self.create_json_message({"error": f"No pixel data: {exc}"})
            return

        info = {
            "shape": tuple(int(x) for x in arr.shape),
            "dtype": str(arr.dtype),
            "min": float(np.min(arr)) if arr.size else None,
            "max": float(np.max(arr)) if arr.size else None,
            "mean": float(np.mean(arr)) if arr.size else None,
            "std": float(np.std(arr)) if arr.size else None,
        }

        if include_preview:
            preview = self._generate_preview(ds, arr, preview_frame, max_preview_edge, filename)
            if "blob" in preview:
                blob = preview.pop("blob")
                yield self.create_blob_message(blob=blob, meta={
                    "mime_type": "image/png",
                    "filename": preview.get("filename", "preview.png"),
                })
            info["preview"] = preview

        yield self.create_json_message(info)

    def _generate_preview(self, ds, arr: np.ndarray, desired_frame: int, max_edge: int, original_filename: str) -> dict[str, Any]:
        frame, actual_idx = self._select_frame(ds, arr, desired_frame)
        frame = np.squeeze(frame)
        if frame.ndim not in (2, 3):
            return {"error": f"Unsupported frame shape {tuple(frame.shape)}"}

        mode = "L"
        if frame.ndim == 3:
            # Move channels to last if needed
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
        max_edge = max(self.PREVIEW_MIN_EDGE, min(max_edge, self.PREVIEW_MAX_EDGE))
        resampling = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
        # enforce a conservative blob size cap (8 MB)
        MAX_BLOB_BYTES = 8 * 1024 * 1024
        current_edge = int(max_edge)
        blob = None
        pw = ph = None
        while current_edge >= self.PREVIEW_MIN_EDGE:
            img = image.copy()
            img.thumbnail((current_edge, current_edge), resampling)
            b = BytesIO()
            try:
                img.save(b, format="PNG", optimize=True)
            except Exception:
                img.save(b, format="PNG")
            d = b.getvalue()
            if len(d) <= MAX_BLOB_BYTES or current_edge == self.PREVIEW_MIN_EDGE:
                blob = d
                pw, ph = img.width, img.height
                break
            current_edge = max(self.PREVIEW_MIN_EDGE, int(current_edge * 0.75))
        name = (original_filename.rsplit(".", 1)[0] or "dicom") + f"_frame_{actual_idx}.png"
        return {
            "frame_index": int(actual_idx),
            "preview_width": int(pw or image.width),
            "preview_height": int(ph or image.height),
            "filename": name,
            "mime_type": "image/png",
            "blob": blob or b"",
        }

    def _select_frame(self, ds, arr: np.ndarray, desired_frame: int):
        num_frames = int(getattr(ds, "NumberOfFrames", 1) or 1)
        if arr.ndim >= 4:
            frames = arr.shape[0]
            idx = max(0, min(int(desired_frame), frames - 1))
            return arr[idx], idx
        if arr.ndim == 3 and num_frames > 1 and arr.shape[0] == num_frames:
            frames = arr.shape[0]
            idx = max(0, min(int(desired_frame), frames - 1))
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
        data = (data - vmin) / (vmax - vmin)
        data = np.clip(data * 255.0, 0, 255).astype(np.uint8)
        return data

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
