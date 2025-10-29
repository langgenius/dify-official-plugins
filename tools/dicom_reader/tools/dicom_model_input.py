from __future__ import annotations

from io import BytesIO
from typing import Any

import numpy as np
import pydicom
from PIL import Image
from dify_plugin import Tool


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

        frame_index = self._as_int(tool_parameters.get("frame_index"), 0)
        channels_first = self._as_bool(tool_parameters.get("channels_first"), True)
        normalize_01 = self._as_bool(tool_parameters.get("normalize_0_1"), True)
        include_preview = self._as_bool(tool_parameters.get("include_preview_image"), False)
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
            arr = np.asarray(ds.pixel_array)
        except Exception as exc:  # pylint: disable=broad-except
            yield self.create_text_message(f"No pixel array: {exc}")
            return

        frame, _ = self._select_frame(arr, ds, frame_index)
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
            image = Image.fromarray(img8 if img8.ndim == 2 else img8.astype(np.uint8), mode="L" if img8.ndim == 2 else "RGB")
            resampling = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
            MAX_BLOB_BYTES = 8 * 1024 * 1024
            current_edge = int(max_edge)
            blob = None
            pw = ph = None
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
                    pw, ph = img.width, img.height
                    break
                current_edge = max(32, int(current_edge * 0.75))
            preview = {
                "preview_width": image.width,
                "preview_height": image.height,
                "mime_type": "image/png",
                "filename": (filename.rsplit(".", 1)[0] or "dicom") + "_model_input.png",
            }
            yield self.create_blob_message(blob=blob or b"", meta={
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
