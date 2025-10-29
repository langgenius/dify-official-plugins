from __future__ import annotations

from typing import Any
from io import BytesIO

import numpy as np
import pydicom
from dify_plugin import Tool

from ._utils import as_bool, as_int, make_preview_png_bytes, select_frame


class DicomMultiframeTool(Tool):
    """
    Inspect multi-frame DICOMs: report number of frames and preview a given frame.
    """

    def _invoke(self, tool_parameters: dict[str, Any]):
        file_obj = tool_parameters.get("dicom_file")
        if not file_obj:
            yield self.create_text_message("`dicom_file` is required.")
            return

        with_shapes = as_bool(tool_parameters.get("include_shapes"), False)
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
        frame, idx = select_frame(ds, arr, frame_index)
        frame = np.squeeze(frame)
        blob, pw, ph = make_preview_png_bytes(frame, max_edge)
        name = (original_filename.rsplit(".", 1)[0] or "dicom") + f"_frame_{idx}.png"
        return {
            "frame_index": int(idx),
            "preview_width": int(pw),
            "preview_height": int(ph),
            "mime_type": "image/png",
            "filename": name,
            "blob": blob,
        }
