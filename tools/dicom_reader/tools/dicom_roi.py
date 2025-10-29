from __future__ import annotations

import json
from typing import Any
from io import BytesIO

import numpy as np
import pydicom
from dify_plugin import Tool

from ._utils import as_bool, as_int, make_preview_png_bytes, select_frame, to_uint8_minmax


class DicomROITool(Tool):
    """
    Analyze a rectangular ROI: compute stats within the region and optionally return a preview with the ROI outlined.
    """

    def _invoke(self, tool_parameters: dict[str, Any]):
        file_obj = tool_parameters.get("dicom_file")
        if not file_obj:
            yield self.create_text_message("`dicom_file` is required.")
            return

        frame_index = as_int(tool_parameters.get("frame_index"), 0)
        roi_json = tool_parameters.get("roi_bbox")
        include_preview = as_bool(tool_parameters.get("include_preview_image"), True)
        max_edge = as_int(tool_parameters.get("max_preview_edge"), 256)

        if not isinstance(roi_json, str) or not roi_json.strip():
            yield self.create_text_message("`roi_bbox` (JSON) is required: {\"x\",\"y\",\"width\",\"height\"}.")
            return

        try:
            roi = json.loads(roi_json)
        except Exception as exc:  # pylint: disable=broad-except
            yield self.create_text_message(f"Invalid ROI JSON: {exc}")
            return

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
            yield self.create_text_message(f"No pixel array: {exc}")
            return

        frame, idx = select_frame(ds, arr, frame_index)
        img = frame.astype(np.float32)
        if img.ndim > 2:
            img = img[..., 0]

        x0 = max(0, int(roi.get("x", 0)))
        y0 = max(0, int(roi.get("y", 0)))
        w = max(1, int(roi.get("width", 1)))
        h = max(1, int(roi.get("height", 1)))
        x1 = min(img.shape[1], x0 + w)
        y1 = min(img.shape[0], y0 + h)
        if x0 >= x1 or y0 >= y1:
            yield self.create_text_message("ROI out of bounds or empty.")
            return

        roi_img = img[y0:y1, x0:x1]
        stats = {
            "frame_index": int(idx),
            "roi": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0},
            "min": float(np.min(roi_img)),
            "max": float(np.max(roi_img)),
            "mean": float(np.mean(roi_img)),
            "std": float(np.std(roi_img)),
            "area_pixels": int(roi_img.size),
        }

        if include_preview:
            base = to_uint8_minmax(img)
            rgb = np.stack([base, base, base], axis=-1)
            # draw rectangle border in red
            rgb[y0:y1, x0] = [255, 0, 0]
            rgb[y0:y1, x1 - 1] = [255, 0, 0]
            rgb[y0, x0:x1] = [255, 0, 0]
            rgb[y1 - 1, x0:x1] = [255, 0, 0]
            blob, pw, ph = make_preview_png_bytes(rgb.astype(np.uint8), max_edge)
            preview = {
                "preview_width": int(pw),
                "preview_height": int(ph),
                "mime_type": "image/png",
                "filename": (filename.rsplit(".", 1)[0] or "dicom") + f"_roi_{idx}.png",
            }
            yield self.create_blob_message(blob=blob, meta={
                "mime_type": preview["mime_type"],
                "filename": preview["filename"],
            })
            yield self.create_json_message({"stats": stats, "preview": preview})
        else:
            yield self.create_json_message({"stats": stats})

    # duplicate helpers removed; using shared utils
