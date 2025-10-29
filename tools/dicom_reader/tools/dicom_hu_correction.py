from __future__ import annotations

from io import BytesIO
from typing import Any

import numpy as np
import pydicom
from PIL import Image
from dify_plugin import Tool


class DicomHUCorrectionTool(Tool):
    """
    Apply RescaleSlope and RescaleIntercept to convert pixel values to HU-like intensities.
    Returns basic stats and an optional normalized preview of the converted frame.
    """

    def _invoke(self, tool_parameters: dict[str, Any]):
        file_obj = tool_parameters.get("dicom_file")
        if not file_obj:
            yield self.create_text_message("`dicom_file` is required.")
            return

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
            yield self.create_json_message({"error": f"No pixel data: {exc}"})
            return

        slope = float(getattr(ds, "RescaleSlope", 1.0) or 1.0)
        intercept = float(getattr(ds, "RescaleIntercept", 0.0) or 0.0)

        frame, idx = self._select_frame(arr, ds, frame_index)
        hu = frame.astype(np.float32) * slope + intercept

        result: dict[str, Any] = {
            "frame_index": int(idx),
            "slope": slope,
            "intercept": intercept,
            "min": float(np.min(hu)) if hu.size else None,
            "max": float(np.max(hu)) if hu.size else None,
            "mean": float(np.mean(hu)) if hu.size else None,
            "std": float(np.std(hu)) if hu.size else None,
        }

        if include_preview:
            img8 = self._normalize_to_uint8(hu)
            image = Image.fromarray(img8, mode="L")
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
            preview = {
                "preview_width": image.width,
                "preview_height": image.height,
                "mime_type": "image/png",
                "filename": (filename.rsplit(".", 1)[0] or "dicom") + f"_hu_{idx}.png",
            }
            yield self.create_blob_message(blob=blob or b"", meta={
                "mime_type": preview["mime_type"],
                "filename": preview["filename"],
            })
            result["preview"] = preview

        yield self.create_json_message(result)

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
        data = (data - vmin) / (vmax - vmin)
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
