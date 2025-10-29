from __future__ import annotations

from io import BytesIO
from typing import Any

import numpy as np
import pydicom
from PIL import Image
from dify_plugin import Tool


class DicomThresholdMaskTool(Tool):
    """
    Build a threshold-based binary mask and return counts with an overlay preview.
    """

    def _invoke(self, tool_parameters: dict[str, Any]):
        file_obj = tool_parameters.get("dicom_file")
        if not file_obj:
            yield self.create_text_message("`dicom_file` is required.")
            return

        frame_index = self._as_int(tool_parameters.get("frame_index"), 0)
        thr_lo = self._as_float(tool_parameters.get("threshold_lower"), None)
        thr_hi = self._as_float(tool_parameters.get("threshold_upper"), None)
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
            arr = np.asarray(ds.pixel_array).astype(np.float32)
        except Exception as exc:  # pylint: disable=broad-except
            yield self.create_json_message({"error": f"No pixel array: {exc}"})
            return

        frame, idx = self._select_frame(arr, ds, frame_index)
        mask = self._threshold(frame, thr_lo, thr_hi)
        count = int(np.count_nonzero(mask))

        # Build overlay preview
        base = self._to_uint8(frame)
        rgb = np.stack([base, base, base], axis=-1)
        overlay = rgb.copy()
        # Red overlay for mask pixels (alpha blend 50%)
        red = np.zeros_like(rgb)
        red[..., 0] = 255
        alpha = 0.5
        overlay[mask] = (alpha * red[mask] + (1 - alpha) * overlay[mask]).astype(np.uint8)
        image = Image.fromarray(overlay, mode="RGB")
        resampling = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
        MAX_BLOB_BYTES = 8 * 1024 * 1024
        current_edge = int(max_edge)
        blob = None
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
                image = img
                break
            current_edge = max(32, int(current_edge * 0.75))
        meta = {
            "frame_index": int(idx),
            "mask_pixels": count,
            "mime_type": "image/png",
            "filename": (filename.rsplit(".", 1)[0] or "dicom") + f"_mask_{idx}.png",
        }
        yield self.create_blob_message(blob=blob or b"", meta={
            "mime_type": meta["mime_type"],
            "filename": meta["filename"],
        })
        yield self.create_json_message(meta)

    def _threshold(self, x: np.ndarray, lo: float | None, hi: float | None) -> np.ndarray:
        if lo is None and hi is None:
            t = float(np.mean(x))
            return x > t
        mask = np.ones_like(x, dtype=bool)
        if lo is not None:
            mask &= x >= float(lo)
        if hi is not None:
            mask &= x <= float(hi)
        return mask

    def _to_uint8(self, x: np.ndarray) -> np.ndarray:
        data = x.astype(np.float32)
        vmin = float(np.min(data))
        vmax = float(np.max(data))
        if vmax == vmin:
            return np.zeros_like(data, dtype=np.uint8)
        data = (data - vmin) / (vmax - vmin)
        return np.clip(data * 255.0, 0, 255).astype(np.uint8)

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

    def _as_int(self, value: Any, default: int = 0) -> int:
        if value is None:
            return default
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    def _as_float(self, value: Any, default: float | None) -> float | None:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
