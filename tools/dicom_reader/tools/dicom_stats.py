from __future__ import annotations

import json
from typing import Any
from io import BytesIO

import numpy as np
import pydicom
from dify_plugin import Tool

from ._utils import as_int, select_frame


class DicomStatsTool(Tool):
    """
    Compute basic statistics (mean, variance, std) and a histogram over the pixel data
    or a rectangular ROI when provided.
    """

    def _invoke(self, tool_parameters: dict[str, Any]):
        file_obj = tool_parameters.get("dicom_file")
        if not file_obj:
            yield self.create_text_message("`dicom_file` is required.")
            return

        frame_index = as_int(tool_parameters.get("frame_index"), 0)
        bins = self._as_int(tool_parameters.get("hist_bins"), 64)
        roi_json = tool_parameters.get("roi_bbox")

        roi = None
        if isinstance(roi_json, str) and roi_json.strip():
            try:
                roi = json.loads(roi_json)
            except Exception:  # pylint: disable=broad-except
                roi = None

        blob = getattr(file_obj, "blob", None)
        if blob is None:
            yield self.create_text_message("Unable to read the uploaded file.")
            return

        try:
            ds = pydicom.dcmread(BytesIO(blob), stop_before_pixels=False, force=True)
        except Exception as exc:  # pylint: disable=broad-except
            yield self.create_text_message(f"Failed to parse DICOM: {exc}")
            return

        try:
            arr = np.asarray(ds.pixel_array)
        except Exception as exc:  # pylint: disable=broad-except
            yield self.create_json_message({"error": f"No pixel array: {exc}"})
            return

        frame, _ = select_frame(ds, arr, frame_index)
        x = frame.astype(np.float32)
        if x.ndim > 2:
            x = x[..., 0]

        if roi and all(k in roi for k in ("x", "y", "width", "height")):
            x0 = max(0, int(roi["x"]))
            y0 = max(0, int(roi["y"]))
            w = max(1, int(roi["width"]))
            h = max(1, int(roi["height"]))
            x = x[y0:y0 + h, x0:x0 + w]

        if x.size == 0:
            yield self.create_json_message({"error": "Empty ROI/pixel data"})
            return

        stats = {
            "min": float(np.min(x)),
            "max": float(np.max(x)),
            "mean": float(np.mean(x)),
            "variance": float(np.var(x)),
            "std": float(np.std(x)),
        }

        # Histogram (counts only, with min/max range)
        try:
            hist, edges = np.histogram(x, bins=bins)
            stats["histogram"] = {
                "bins": int(bins),
                "counts": hist.astype(int).tolist(),
                "min_edge": float(edges[0]),
                "max_edge": float(edges[-1]),
            }
        except Exception:  # pylint: disable=broad-except
            pass

        yield self.create_json_message(stats)

    def _as_int(self, value: Any, default: int = 0) -> int:  # backward compat, unused
        return as_int(value, default)
