from __future__ import annotations

from io import BytesIO
from typing import Any

import numpy as np
import pydicom
from PIL import Image
from dify_plugin import Tool

from ._utils import as_int, make_preview_png_bytes, select_frame, to_uint8_minmax


class DicomPixelOpsTool(Tool):
    """
    Perform simple pixel operations on a selected frame: normalize, add/subtract scalar,
    clip, contrast stretch, or box blur. Returns stats and a preview image.
    """

    def _invoke(self, tool_parameters: dict[str, Any]):
        file_obj = tool_parameters.get("dicom_file")
        if not file_obj:
            yield self.create_text_message("`dicom_file` is required.")
            return

        op = (tool_parameters.get("operation") or "normalize").strip().lower()
        frame_index = as_int(tool_parameters.get("frame_index"), 0)
        value = self._as_float(tool_parameters.get("value"), 0.0)
        min_v = self._as_float(tool_parameters.get("min_value"), None)
        max_v = self._as_float(tool_parameters.get("max_value"), None)
        ksize = max(1, as_int(tool_parameters.get("kernel_size"), 3))
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

        frame, idx = select_frame(ds, arr, frame_index)
        data = frame.astype(np.float32)

        if op == "normalize":
            out = self._normalize(data)
        elif op == "add":
            out = data + float(value)
        elif op == "subtract":
            out = data - float(value)
        elif op == "clip":
            lo = -np.inf if min_v is None else float(min_v)
            hi = np.inf if max_v is None else float(max_v)
            out = np.clip(data, lo, hi)
        elif op == "contrast_stretch":
            p1, p99 = np.percentile(data, [1, 99])
            if p99 == p1:
                out = np.zeros_like(data)
            else:
                out = np.clip((data - p1) / (p99 - p1), 0, 1)
        elif op == "box_blur":
            out = self._box_blur(data, ksize)
        else:
            out = self._normalize(data)

        stats = {
            "frame_index": int(idx),
            "operation": op,
            "min": float(np.min(out)) if out.size else None,
            "max": float(np.max(out)) if out.size else None,
            "mean": float(np.mean(out)) if out.size else None,
            "std": float(np.std(out)) if out.size else None,
        }

        img8 = to_uint8_minmax(out)
        blob, pw, ph = make_preview_png_bytes(img8, max_edge)
        preview = {
            "preview_width": int(pw),
            "preview_height": int(ph),
            "mime_type": "image/png",
            "filename": (filename.rsplit(".", 1)[0] or "dicom") + f"_{op}_{idx}.png",
        }
        yield self.create_blob_message(blob=blob, meta={
            "mime_type": preview["mime_type"],
            "filename": preview["filename"],
        })
        yield self.create_json_message({"result": stats, "preview": preview})

    def _normalize(self, x: np.ndarray) -> np.ndarray:
        vmin = float(np.min(x))
        vmax = float(np.max(x))
        if vmax == vmin:
            return np.zeros_like(x)
        return (x - vmin) / (vmax - vmin)

    def _box_blur(self, x: np.ndarray, k: int) -> np.ndarray:
        # Simple separable box blur using cumulative sums (O(n))
        if k <= 1:
            return x.copy()
        if x.ndim != 2:
            x2d = x.reshape(x.shape[-2], x.shape[-1]) if x.ndim > 2 else x
        else:
            x2d = x
        pad = k // 2
        # Horizontal
        c = np.cumsum(np.pad(x2d, ((0, 0), (1, 0)), mode='edge'), axis=1)
        h = (c[:, k:] - c[:, :-k]) / k
        # Vertical
        c2 = np.cumsum(np.pad(h, ((1, 0), (0, 0)), mode='edge'), axis=0)
        v = (c2[k:, :] - c2[:-k, :]) / k
        return v

    def _as_int(self, value: Any, default: int = 0) -> int:  # backward compat, unused
        return as_int(value, default)

    def _as_float(self, value: Any, default: float | None) -> float | None:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
