from __future__ import annotations

from io import BytesIO
from typing import Any

import numpy as np
import pydicom
from dify_plugin import Tool


class DicomVolumeTool(Tool):
    """
    Estimate volume and density using pixel spacing and slice thickness.
    Builds a binary mask using a threshold (or range) and multiplies voxel count by voxel volume.
    """

    def _invoke(self, tool_parameters: dict[str, Any]):
        file_obj = tool_parameters.get("dicom_file")
        if not file_obj:
            yield self.create_text_message("`dicom_file` is required.")
            return

        frame_index = self._as_int(tool_parameters.get("frame_index"), None)
        thr_lo = self._as_float(tool_parameters.get("threshold_lower"), None)
        thr_hi = self._as_float(tool_parameters.get("threshold_upper"), None)

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
            arr = np.asarray(ds.pixel_array).astype(np.float32)
        except Exception as exc:  # pylint: disable=broad-except
            yield self.create_json_message({"error": f"No pixel array: {exc}"})
            return

        # Attempt HU correction if tags exist
        slope = float(getattr(ds, "RescaleSlope", 1.0) or 1.0)
        intercept = float(getattr(ds, "RescaleIntercept", 0.0) or 0.0)
        arr = arr * slope + intercept

        # Determine voxel size
        dx, dy = 1.0, 1.0
        spacing = getattr(ds, "PixelSpacing", None)
        if isinstance(spacing, (list, tuple)) and len(spacing) >= 2:
            try:
                dx, dy = float(spacing[0]), float(spacing[1])
            except Exception:
                pass
        dz = None
        for tag in ("SliceThickness", "SpacingBetweenSlices"):
            val = getattr(ds, tag, None)
            if val is not None:
                try:
                    dz = float(val)
                    break
                except Exception:
                    continue
        if dz is None:
            dz = 1.0

        # Select a frame or operate across frames if available
        num_frames = int(getattr(ds, "NumberOfFrames", 1) or 1)
        if arr.ndim >= 4:  # assume first dim is frames
            if frame_index is None:
                mask_volume, mean_val = self._volume_over_frames(arr, thr_lo, thr_hi)
                frames_used = arr.shape[0]
            else:
                idx = max(0, min(int(frame_index), arr.shape[0] - 1))
                mask = self._threshold(arr[idx], thr_lo, thr_hi)
                mask_volume = int(np.count_nonzero(mask))
                mean_val = float(np.mean(arr[idx][mask])) if np.any(mask) else None
                frames_used = 1
        elif arr.ndim == 3 and num_frames > 1 and arr.shape[0] == num_frames:
            if frame_index is None:
                mask_volume, mean_val = self._volume_over_frames(arr, thr_lo, thr_hi)
                frames_used = arr.shape[0]
            else:
                idx = max(0, min(int(frame_index), arr.shape[0] - 1))
                mask = self._threshold(arr[idx], thr_lo, thr_hi)
                mask_volume = int(np.count_nonzero(mask))
                mean_val = float(np.mean(arr[idx][mask])) if np.any(mask) else None
                frames_used = 1
        else:
            mask = self._threshold(arr, thr_lo, thr_hi)
            mask_volume = int(np.count_nonzero(mask))
            mean_val = float(np.mean(arr[mask])) if np.any(mask) else None
            frames_used = 1

        # Physical volume
        voxel_volume = float(dx * dy * dz)
        volume_mm3 = float(mask_volume) * voxel_volume

        result = {
            "frames_used": int(frames_used),
            "voxel_size_mm": [dx, dy, dz],
            "voxel_volume_mm3": voxel_volume,
            "threshold_lower": thr_lo,
            "threshold_upper": thr_hi,
            "mask_voxels": int(mask_volume),
            "volume_mm3": volume_mm3,
            "mean_intensity_in_mask": mean_val,
        }
        yield self.create_json_message(result)

    def _threshold(self, x: np.ndarray, lo: float | None, hi: float | None) -> np.ndarray:
        if lo is None and hi is None:
            # default simple threshold at mean
            t = float(np.mean(x))
            return x > t
        mask = np.ones_like(x, dtype=bool)
        if lo is not None:
            mask &= x >= float(lo)
        if hi is not None:
            mask &= x <= float(hi)
        return mask

    def _volume_over_frames(self, arr: np.ndarray, lo: float | None, hi: float | None) -> tuple[int, float | None]:
        total = 0
        vals = []
        for i in range(arr.shape[0]):
            m = self._threshold(arr[i], lo, hi)
            c = int(np.count_nonzero(m))
            total += c
            if c > 0:
                vals.append(float(np.mean(arr[i][m])))
        return total, (float(np.mean(vals)) if vals else None)

    def _as_int(self, value: Any, default: int | None) -> int | None:
        if value is None:
            return default
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    def _as_float(self, value: Any, default: float | None) -> float | None:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

