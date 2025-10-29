from __future__ import annotations

import json
from io import BytesIO
from typing import Any

import numpy as np
import pydicom
from PIL import Image
from dify_plugin import Tool


class DicomROITool(Tool):
    """
    Analyze a rectangular ROI: compute stats within the region and optionally return a preview with the ROI outlined.
    """

    def _invoke(self, tool_parameters: dict[str, Any]):
        file_obj = tool_parameters.get("dicom_file")
        if not file_obj:
            yield self.create_text_message("`dicom_file` is required.")
            return

        frame_index = self._as_int(tool_parameters.get("frame_index"), 0)
        roi_json = tool_parameters.get("roi_bbox")
        include_preview = self._as_bool(tool_parameters.get("include_preview_image"), True)
        max_edge = self._as_int(tool_parameters.get("max_preview_edge"), 256)

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

        frame, idx = self._select_frame(arr, ds, frame_index)
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
            base = self._to_uint8(img)
            rgb = np.stack([base, base, base], axis=-1)
            # draw rectangle border in red
            rgb[y0:y1, x0] = [255, 0, 0]
            rgb[y0:y1, x1 - 1] = [255, 0, 0]
            rgb[y0, x0:x1] = [255, 0, 0]
            rgb[y1 - 1, x0:x1] = [255, 0, 0]
            image = Image.fromarray(rgb.astype(np.uint8), mode="RGB")
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
            preview = {
                "preview_width": image.width,
                "preview_height": image.height,
                "mime_type": "image/png",
                "filename": (filename.rsplit(".", 1)[0] or "dicom") + f"_roi_{idx}.png",
            }
            yield self.create_blob_message(blob=blob or b"", meta={
                "mime_type": preview["mime_type"],
                "filename": preview["filename"],
            })
            yield self.create_json_message({"stats": stats, "preview": preview})
        else:
            yield self.create_json_message({"stats": stats})

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

    def _to_uint8(self, x: np.ndarray) -> np.ndarray:
        data = x.astype(np.float32)
        vmin = float(np.min(data))
        vmax = float(np.max(data))
        if vmax == vmin:
            return np.zeros_like(data, dtype=np.uint8)
        data = (data - vmin) / (vmax - vmin)
        return np.clip(data * 255.0, 0, 255).astype(np.uint8)

    def _as_int(self, value: Any, default: int = 0) -> int:
        if value is None:
            return default
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

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
