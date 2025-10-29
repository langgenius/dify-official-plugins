from __future__ import annotations

from io import BytesIO
from typing import Any

import numpy as np
import pydicom
from dify_plugin import Tool


class DicomSpatialInfoTool(Tool):
    """
    Extract spatial geometry information: pixel spacing, slice thickness, spacing between slices,
    image orientation (patient), image position (patient), and derived voxel size/volume when possible.
    """

    def _invoke(self, tool_parameters: dict[str, Any]):
        file_obj = tool_parameters.get("dicom_file")
        if not file_obj:
            yield self.create_text_message("`dicom_file` is required.")
            return

        blob = getattr(file_obj, "blob", None)
        if blob is None:
            yield self.create_text_message("Unable to read the uploaded file.")
            return

        try:
            ds = pydicom.dcmread(BytesIO(blob), stop_before_pixels=True, force=True)
        except Exception as exc:  # pylint: disable=broad-except
            yield self.create_text_message(f"Failed to parse DICOM: {exc}")
            return

        info: dict[str, Any] = {}

        def as_list(x):
            try:
                return [float(v) for v in list(x)]
            except Exception:
                try:
                    return [float(x)]
                except Exception:
                    return None

        spacing = getattr(ds, "PixelSpacing", None)
        thickness = getattr(ds, "SliceThickness", None)
        sbs = getattr(ds, "SpacingBetweenSlices", None)
        iop = getattr(ds, "ImageOrientationPatient", None)
        ipp = getattr(ds, "ImagePositionPatient", None)

        if spacing is not None:
            info["pixel_spacing_mm"] = as_list(spacing)
        if thickness is not None:
            try:
                info["slice_thickness_mm"] = float(thickness)
            except Exception:
                info["slice_thickness_mm"] = None
        if sbs is not None:
            try:
                info["spacing_between_slices_mm"] = float(sbs)
            except Exception:
                info["spacing_between_slices_mm"] = None
        if iop is not None:
            info["image_orientation_patient"] = as_list(iop)
        if ipp is not None:
            info["image_position_patient"] = as_list(ipp)

        # Derived voxel size and volume (mm^3)
        voxel_mm = None
        if isinstance(spacing, (list, tuple)) and (thickness is not None or sbs is not None):
            try:
                dx, dy = float(spacing[0]), float(spacing[1])
                dz = float(thickness if thickness is not None else sbs)
                voxel_mm = [dx, dy, dz]
                info["voxel_size_mm"] = voxel_mm
                info["voxel_volume_mm3"] = float(dx * dy * dz)
            except Exception:
                pass

        # Include matrix size if available
        rows = getattr(ds, "Rows", None)
        cols = getattr(ds, "Columns", None)
        if rows is not None and cols is not None:
            info["matrix"] = [int(rows), int(cols)]

        yield self.create_json_message(info)

