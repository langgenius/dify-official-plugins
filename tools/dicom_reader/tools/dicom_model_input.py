from __future__ import annotations

from typing import Any
from io import BytesIO

import numpy as np
import pydicom
from PIL import Image
from dify_plugin import Tool

from ._utils import as_bool, as_int, make_preview_png_bytes, select_frame


class DicomModelInputTool(Tool):
    """
    Prepare image data to feed into AI models with a standard shape.
    Reports the transformed shape [1, C, H, W] and optionally emits a preview.
    """

    def _invoke(self, tool_parameters: dict[str, Any]):
        file_obj = tool_parameters.get("dicom_file")
        if not file_obj:
            yield self.create_text_message("`dicom_file` is required.")
            return

        frame_index = as_int(tool_parameters.get("frame_index"), 0)
        channels_first = as_bool(tool_parameters.get("channels_first"), True)
        normalize_01 = as_bool(tool_parameters.get("normalize_0_1"), True)
        include_preview = as_bool(tool_parameters.get("include_preview_image"), False)
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
            yield self.create_text_message(f"No pixel array: {exc}")
            return

        frame, _ = select_frame(ds, arr, frame_index)
        x = frame.astype(np.float32)

        # Ensure 2D/3D (channels last if multi-channel)
        if x.ndim == 2:
            c = 1
            h, w = x.shape
            if normalize_01:
                x = self._normalize(x)
            if channels_first:
                out_shape = [1, c, h, w]
            else:
                out_shape = [1, h, w, c]
        elif x.ndim == 3:
            # Move channels to last if likely channel-first
            if x.shape[0] in (3, 4) and x.shape[-1] not in (3, 4):
                x = np.moveaxis(x, 0, -1)
            h, w, c = x.shape[0], x.shape[1], x.shape[2] if x.ndim == 3 else (x.shape[0], x.shape[1], 1)
            if normalize_01:
                x = self._normalize(x)
            if channels_first:
                out_shape = [1, c, h, w]
            else:
                out_shape = [1, h, w, c]
        else:
            # Fallback: squeeze and treat as grayscale
            x = np.squeeze(x)
            if x.ndim != 2:
                yield self.create_json_message({"error": f"Unsupported pixel shape {tuple(frame.shape)}"})
                return
            h, w = x.shape
            if normalize_01:
                x = self._normalize(x)
            out_shape = [1, 1, h, w] if channels_first else [1, h, w, 1]

        result = {
            "input_shape": out_shape,
            "channels_first": bool(channels_first),
            "normalized_0_1": bool(normalize_01),
            "dtype": "float32",
        }

        if include_preview:
            img8 = self._to_uint8(x)
            # If channels_first, map to HWC for preview
            if channels_first:
                if len(out_shape) == 4 and out_shape[1] in (1, 3):
                    if out_shape[1] == 1:
                        img8 = img8[0]
                    else:
                        img8 = np.moveaxis(img8, 0, -1)
            blob, pw, ph = make_preview_png_bytes(img8, max_edge)
            preview = {
                "preview_width": image.width,
                "preview_height": image.height,
                "mime_type": "image/png",
                "filename": (filename.rsplit(".", 1)[0] or "dicom") + "_model_input.png",
            }
            yield self.create_blob_message(blob=blob, meta={
                "mime_type": preview["mime_type"],
                "filename": preview["filename"],
            })
            result["preview"] = preview

        yield self.create_json_message(result)

    def _normalize(self, x: np.ndarray) -> np.ndarray:
        vmin = float(np.min(x))
        vmax = float(np.max(x))
        if vmax == vmin:
            return np.zeros_like(x)
        return (x - vmin) / (vmax - vmin)

    def _to_uint8(self, x: np.ndarray) -> np.ndarray:
        if x.dtype != np.float32:
            x = x.astype(np.float32)
        x = np.clip(x, 0, 1)
        x = (x * 255.0).astype(np.uint8)
        if x.ndim == 3 and x.shape[2] not in (1, 3):
            # Project to single channel for preview
            x = x[..., 0]
        if x.ndim == 3 and x.shape[2] == 1:
            x = x[..., 0]
        return x

    def _as_int(self, value: Any, default: int = 0) -> int:  # backward compat, unused
        return as_int(value, default)

    def _as_bool(self, value: Any, default: bool = False) -> bool:  # backward compat, unused
        return as_bool(value, default)
