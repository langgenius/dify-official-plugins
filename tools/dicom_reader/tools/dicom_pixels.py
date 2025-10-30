from __future__ import annotations

from typing import Any
from io import BytesIO

import numpy as np
import pydicom
from dify_plugin import Tool

from ._utils import as_bool, as_int, make_preview_png_bytes, select_frame


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

        include_preview = as_bool(tool_parameters.get("include_preview_image"), False)
        preview_frame = as_int(tool_parameters.get("preview_frame_index"), 0)
        max_preview_edge = as_int(tool_parameters.get("max_preview_edge"), 256)

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
        frame, actual_idx = select_frame(ds, arr, desired_frame)
        frame = np.squeeze(frame)
        if frame.ndim not in (2, 3):
            return {"error": f"Unsupported frame shape {tuple(frame.shape)}"}

        blob, pw, ph = make_preview_png_bytes(frame, max_edge)
        name = (original_filename.rsplit(".", 1)[0] or "dicom") + f"_frame_{actual_idx}.png"
        return {
            "frame_index": int(actual_idx),
            "preview_width": int(pw),
            "preview_height": int(ph),
            "filename": name,
            "mime_type": "image/png",
            "blob": blob,
        }
