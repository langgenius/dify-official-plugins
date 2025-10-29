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

        extra_tags = self._parse_additional_tags(tool_parameters.get("additional_tags", ""))

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
            "file": self._file_stats(dataset, file_size, filename),
            "patient": self._collect_named_fields(dataset, self.PATIENT_FIELDS),
            "study": self._collect_named_fields(dataset, self.STUDY_FIELDS),
            "series": self._collect_named_fields(dataset, self.SERIES_FIELDS),
            "image": self._collect_named_fields(dataset, self.IMAGE_FIELDS),
        }

        additional = self._collect_additional_tags(dataset, extra_tags)
        if additional:
            metadata["additional_tags"] = additional

        yield self.create_json_message(metadata)

    # Helpers
    def _collect_named_fields(self, dataset: pydicom.dataset.Dataset, fields: tuple[str, ...]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in fields:
            if not hasattr(dataset, name):
                continue
            value = getattr(dataset, name, None)
            if value is None:
                continue
            formatted = self._format_value(value)
            if formatted is not None and formatted != "":
                result[self._display_name(name)] = formatted
        return result

    def _collect_additional_tags(
        self,
        dataset: pydicom.dataset.Dataset,
        requested_tags: list[str],
    ) -> dict[str, Any]:
        collected: dict[str, Any] = {}
        for raw_tag in requested_tags:
            lookup = raw_tag.strip()
            if not lookup:
                continue
            tag = self._parse_tag_keyword(lookup)
            if tag is None or tag not in dataset:
                continue
            data_element = dataset[tag]
            value = self._format_value(data_element.value)
            if value is not None:
                collected[data_element.name] = value
        return collected

    def _parse_tag_keyword(self, lookup: str) -> BaseTag | None:
        hex_match = re.fullmatch(r"\(?\s*([0-9A-Fa-f]{4})[,\\s]+([0-9A-Fa-f]{4})\s*\)?", lookup)
        if hex_match:
            group = int(hex_match.group(1), 16)
            element = int(hex_match.group(2), 16)
            return Tag(group, element)
        cleaned = re.sub(r"[^0-9A-Za-z_]", "", lookup)
        for candidate in {cleaned, cleaned.lower(), cleaned.upper(), cleaned.capitalize()}:
            try:
                tag = tag_for_keyword(candidate)
                if tag:
                    return Tag(tag)
            except Exception:  # pylint: disable=broad-except
                continue
        return None

    def _file_stats(self, dataset: pydicom.dataset.Dataset, size_bytes: int, filename: str) -> dict[str, Any]:
        file_meta = dataset.file_meta if hasattr(dataset, "file_meta") else None
        transfer_uid = getattr(file_meta, "TransferSyntaxUID", None)
        megabytes = size_bytes / (1024 * 1024)
        has_pixel_data = "PixelData" in dataset.keys()
        num_frames = getattr(dataset, "NumberOfFrames", None)
        return {
            "filename": filename,
            "size_bytes": size_bytes,
            "size_megabytes": round(megabytes, 3),
            "transfer_syntax_uid": str(transfer_uid) if transfer_uid else None,
            "transfer_syntax_name": getattr(transfer_uid, "name", None) if isinstance(transfer_uid, UID) else None,
            "is_little_endian": getattr(dataset, "is_little_endian", True),
            "is_implicit_vr": getattr(dataset, "is_implicit_VR", False),
            "has_pixel_data": has_pixel_data,
            "number_of_frames": int(num_frames) if num_frames else 1,
        }

    def _format_value(self, value: Any) -> Any:
        from datetime import date, datetime, time
        from decimal import Decimal
        import math
        import numpy as np
        from pydicom.multival import MultiValue
        try:
            from pydicom.valuerep import PersonNameBase
        except ImportError:  # pragma: no cover
            from pydicom.valuerep import PersonName as PersonNameBase

        if isinstance(value, (int, float, bool)):
            if isinstance(value, float) and not math.isfinite(value):
                return None
            return value
        if isinstance(value, (np.generic,)):
            return value.item()
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, UID):
            return {"uid": str(value), "name": getattr(value, "name", None)}
        if isinstance(value, PersonNameBase):
            return value.original_string or str(value)
        if isinstance(value, (bytes, bytearray)):
            try:
                decoded = value.decode("utf-8", errors="replace")
            except Exception:  # pylint: disable=broad-except
                decoded = str(value)
            return decoded if len(decoded) <= 200 else f"{decoded[:197]}..."
        if isinstance(value, Sequence):
            return {"sequence_length": len(value)}
        if isinstance(value, MultiValue):
            return [self._format_value(item) for item in value[:16]]
        text = str(value)
        return text if len(text) <= 200 else f"{text[:197]}..."

    def _display_name(self, attr_name: str) -> str:
        words = re.findall(r"[A-Z]+[a-z]*|[a-z]+|[0-9]+", attr_name)
        return " ".join(word.capitalize() for word in words)

