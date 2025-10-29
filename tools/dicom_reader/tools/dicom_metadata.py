from __future__ import annotations

import re
from io import BytesIO
from typing import Any

import pydicom
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from pydicom.datadict import tag_for_keyword
from pydicom.errors import InvalidDicomError
from pydicom.sequence import Sequence
from pydicom.tag import BaseTag, Tag
from pydicom.uid import UID

from ._utils import (
    collect_additional_tags,
    collect_named_fields,
    file_stats,
    parse_additional_tags,
)


class DicomMetadataTool(Tool):
    """
    Read a DICOM file and extract key metadata groups plus optional additional tags.
    Output is compact JSON safe for LLM consumption.
    """

    PATIENT_FIELDS = (
        "PatientName",
        "PatientID",
        "PatientSex",
        "PatientBirthDate",
        "PatientAge",
    )
    STUDY_FIELDS = (
        "StudyInstanceUID",
        "StudyDate",
        "StudyTime",
        "AccessionNumber",
        "StudyDescription",
        "ReferringPhysicianName",
    )
    SERIES_FIELDS = (
        "SeriesInstanceUID",
        "SeriesDescription",
        "SeriesNumber",
        "Modality",
        "BodyPartExamined",
        "ProtocolName",
        "Laterality",
    )
    IMAGE_FIELDS = (
        "InstanceNumber",
        "SOPInstanceUID",
        "ImageType",
        "Rows",
        "Columns",
        "NumberOfFrames",
        "SamplesPerPixel",
        "PhotometricInterpretation",
        "BitsAllocated",
        "BitsStored",
        "HighBit",
        "PixelRepresentation",
        "PixelSpacing",
        "SliceThickness",
        "SpacingBetweenSlices",
        "RescaleIntercept",
        "RescaleSlope",
        "WindowCenter",
        "WindowWidth",
    )

    def _invoke(self, tool_parameters: dict[str, Any]) -> "ToolInvokeMessageGenerator":
        file_obj = tool_parameters.get("dicom_file")
        if not file_obj:
            yield self.create_text_message("`dicom_file` is required.")
            return

        extra_tags = parse_additional_tags(tool_parameters.get("additional_tags", ""))

        blob = getattr(file_obj, "blob", None)
        if blob is None:
            yield self.create_text_message("Unable to read the uploaded file.")
            return

        filename = getattr(file_obj, "filename", "dicom_file.dcm")
        file_size = len(blob)

        try:
            dataset = pydicom.dcmread(BytesIO(blob), stop_before_pixels=True, force=True)
        except InvalidDicomError as exc:
            yield self.create_text_message(f"The provided file is not a valid DICOM dataset: {exc}")
            return
        except Exception as exc:  # pylint: disable=broad-except
            yield self.create_text_message(f"Failed to parse DICOM file: {exc}")
            return

        metadata: dict[str, Any] = {
            "file": file_stats(dataset, file_size, filename),
            "patient": collect_named_fields(dataset, self.PATIENT_FIELDS),
            "study": collect_named_fields(dataset, self.STUDY_FIELDS),
            "series": collect_named_fields(dataset, self.SERIES_FIELDS),
            "image": collect_named_fields(dataset, self.IMAGE_FIELDS),
        }

        additional = collect_additional_tags(dataset, extra_tags)
        if additional:
            metadata["additional_tags"] = additional

        yield self.create_json_message(metadata)

