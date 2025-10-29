from __future__ import annotations

from typing import Any
from io import BytesIO

import numpy as np
import pydicom
from dify_plugin import Tool

from ._utils import as_float, as_int, make_preview_png_bytes, select_frame, to_uint8_minmax


class DicomThresholdMaskTool(Tool):
    """
    Build a threshold-based binary mask and return counts with an overlay preview.
    """

    def _invoke(self, tool_parameters: dict[str, Any]):
        file_obj = tool_parameters.get("dicom_file")
        if not file_obj:
            yield self.create_text_message("`dicom_file` is required.")
            return

        frame_index = as_int(tool_parameters.get("frame_index"), 0)
        thr_lo = as_float(tool_parameters.get("threshold_lower"), None)
        thr_hi = as_float(tool_parameters.get("threshold_upper"), None)
        max_edge = as_int(tool_parameters.get("max_preview_edge"), 256)

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

        frame, idx = select_frame(ds, arr, frame_index)
        mask = self._threshold(frame, thr_lo, thr_hi)
        count = int(np.count_nonzero(mask))

        # Build overlay preview
        base = to_uint8_minmax(frame)
        rgb = np.stack([base, base, base], axis=-1)
        overlay = rgb.copy()
        # Red overlay for mask pixels (alpha blend 50%)
        red = np.zeros_like(rgb)
        red[..., 0] = 255
        alpha = 0.5
        overlay[mask] = (alpha * red[mask] + (1 - alpha) * overlay[mask]).astype(np.uint8)
        blob, pw, ph = make_preview_png_bytes(overlay, max_edge)
        meta = {
            "frame_index": int(idx),
            "mask_pixels": count,
            "mime_type": "image/png",
            "filename": (filename.rsplit(".", 1)[0] or "dicom") + f"_mask_{idx}.png",
        }
        yield self.create_blob_message(blob=blob, meta={
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

    def _as_int(self, value: Any, default: int = 0) -> int:  # backward compat, unused
        return as_int(value, default)

    def _as_float(self, value: Any, default: float | None) -> float | None:  # backward compat, unused
        return as_float(value, default)
