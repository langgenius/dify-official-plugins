from __future__ import annotations

from typing import Any
from io import BytesIO

import numpy as np
import pydicom
from dify_plugin import Tool

from ._utils import as_bool, as_int, make_preview_png_bytes, select_frame, to_uint8_minmax


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

        frame_index = as_int(tool_parameters.get("frame_index"), 0)
        include_preview = as_bool(tool_parameters.get("include_preview_image"), True)
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
            arr = np.asarray(ds.pixel_array)
        except Exception as exc:  # pylint: disable=broad-except
            yield self.create_json_message({"error": f"No pixel data: {exc}"})
            return

        slope = float(getattr(ds, "RescaleSlope", 1.0) or 1.0)
        intercept = float(getattr(ds, "RescaleIntercept", 0.0) or 0.0)

        frame, idx = select_frame(ds, arr, frame_index)
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
            # Use util for preview bytes
            blob, pw, ph = make_preview_png_bytes(hu, max_edge)
            preview = {
                "preview_width": int(pw),
                "preview_height": int(ph),
                "mime_type": "image/png",
                "filename": (filename.rsplit(".", 1)[0] or "dicom") + f"_hu_{idx}.png",
            }
            yield self.create_blob_message(blob=blob, meta={
                "mime_type": preview["mime_type"],
                "filename": preview["filename"],
            })
            result["preview"] = preview

        yield self.create_json_message(result)
