import math
import re
from collections.abc import Generator
from datetime import date, datetime, time
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pydicom
from PIL import Image
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from pydicom.datadict import tag_for_keyword
from pydicom.errors import InvalidDicomError
from pydicom.multival import MultiValue
from pydicom.sequence import Sequence
from pydicom.tag import BaseTag, Tag
from pydicom.uid import UID

try:  # pydicom < 3.0 exposes PersonName only
    from pydicom.valuerep import PersonNameBase
except ImportError:  # pragma: no cover - compatibility shim
    from pydicom.valuerep import PersonName as PersonNameBase


class DicomReaderTool(Tool):
    MAX_STAT_SAMPLE_PIXELS = 262_144
    PREVIEW_MIN_EDGE = 32
    PREVIEW_MAX_EDGE = 1024
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

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        file_obj = tool_parameters.get("dicom_file")
        if not file_obj:
            yield self.create_text_message("`dicom_file` is required.")
            return

        include_stats = self._as_bool(tool_parameters.get("include_pixel_statistics"))
        include_preview = self._as_bool(tool_parameters.get("include_preview_image"))
        preview_frame = self._as_int(tool_parameters.get("preview_frame_index"), default=0)
        max_preview_edge = self._as_int(tool_parameters.get("max_preview_edge"), default=256)
        additional_tags = self._parse_additional_tags(tool_parameters.get("additional_tags", ""))

        blob = getattr(file_obj, "blob", None)
        if blob is None:
            yield self.create_text_message("Unable to read the uploaded file.")
            return

        filename = getattr(file_obj, "filename", "dicom_file.dcm")
        file_size = len(blob)
        needs_pixel_data = include_stats or include_preview

        try:
            dataset = pydicom.dcmread(
                BytesIO(blob),
                stop_before_pixels=not needs_pixel_data,
                force=True,
            )
        except InvalidDicomError as exc:
            yield self.create_text_message(f"The provided file is not a valid DICOM dataset: {exc}")
            return
        except Exception as exc:  # pylint: disable=broad-except
            yield self.create_text_message(f"Failed to parse DICOM file: {exc}")
            return

        metadata = self._extract_metadata(dataset, file_size, filename, additional_tags)
        result: dict[str, Any] = {"metadata": metadata}
        summary_notes: list[str] = []

        stats_result: dict[str, Any] | None = None
        if include_stats:
            stats_result = self._extract_pixel_statistics(dataset)
            if "error" in stats_result:
                summary_notes.append(f"Pixel statistics unavailable: {stats_result['error']}")
            else:
                result["pixel_statistics"] = stats_result

        preview_result: dict[str, Any] | None = None
        if include_preview:
            preview_result = self._generate_preview(dataset, preview_frame, max_preview_edge, filename)
            if "error" in preview_result:
                summary_notes.append(f"Preview image unavailable: {preview_result['error']}")
            else:
                blob = preview_result.pop("blob", None)
                if blob:
                    yield self.create_blob_message(
                        blob=blob,
                        meta={
                            "mime_type": preview_result.get("mime_type", "image/png"),
                            "filename": preview_result.get("filename"),
                        },
                    )
                result["preview"] = preview_result

        if additional_tags:
            result["additional_tags"] = metadata.get("additional_tags", {})

        if summary_notes:
            result["notes"] = summary_notes

        yield self.create_json_message(result)
        yield self.create_text_message(self._build_summary(metadata, stats_result, preview_result, summary_notes))

    def _extract_metadata(
        self,
        dataset: pydicom.dataset.Dataset,
        size_bytes: int,
        filename: str,
        additional_tags: list[str],
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "file": self._file_stats(dataset, size_bytes, filename),
            "patient": self._collect_named_fields(dataset, self.PATIENT_FIELDS),
            "study": self._collect_named_fields(dataset, self.STUDY_FIELDS),
            "series": self._collect_named_fields(dataset, self.SERIES_FIELDS),
            "image": self._collect_named_fields(dataset, self.IMAGE_FIELDS),
        }

        additional = self._collect_additional_tags(dataset, additional_tags)
        if additional:
            metadata["additional_tags"] = additional

        metadata["element_counts"] = {
            "total_elements": len(dataset),
            "sequence_elements": sum(1 for elem in dataset if isinstance(elem.value, Sequence)),
        }
        return metadata

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
            if tag is None:
                continue

            if tag not in dataset:
                continue

            data_element = dataset[tag]
            value = self._format_value(data_element.value)
            if value is not None:
                collected[data_element.name] = value
        return collected

    def _parse_tag_keyword(self, lookup: str) -> BaseTag | None:
        # Hex form like 0018,5100 or (0018,5100)
        hex_match = re.fullmatch(r"\(?\s*([0-9A-Fa-f]{4})[,\\s]+([0-9A-Fa-f]{4})\s*\)?", lookup)
        if hex_match:
            group = int(hex_match.group(1), 16)
            element = int(hex_match.group(2), 16)
            return Tag(group, element)

        cleaned = re.sub(r"[^0-9A-Za-z_]", "", lookup)
        candidates = {
            cleaned,
            cleaned.lower(),
            cleaned.upper(),
            cleaned.capitalize(),
        }
        for candidate in candidates:
            try:
                tag = tag_for_keyword(candidate)
                if tag:
                    return Tag(tag)
            except Exception:  # pylint: disable=broad-except
                continue
        return None

    def _file_stats(
        self,
        dataset: pydicom.dataset.Dataset,
        size_bytes: int,
        filename: str,
    ) -> dict[str, Any]:
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

    def _extract_pixel_statistics(self, dataset: pydicom.dataset.Dataset) -> dict[str, Any]:
        try:
            pixel_array = dataset.pixel_array
        except Exception as exc:  # pylint: disable=broad-except
            return {"error": str(exc)}

        flat_pixels = np.asarray(pixel_array).astype(np.float64).ravel()
        total_pixels = flat_pixels.size
        if total_pixels == 0:
            return {"error": "Pixel data is empty."}

        if total_pixels > self.MAX_STAT_SAMPLE_PIXELS:
            indices = np.linspace(0, total_pixels - 1, self.MAX_STAT_SAMPLE_PIXELS, dtype=np.int64)
            sampled = flat_pixels[indices]
            sample_ratio = sampled.size / total_pixels
        else:
            sampled = flat_pixels
            sample_ratio = 1.0

        stats = {
            "pixels_examined": int(sampled.size),
            "total_pixels": int(total_pixels),
            "sample_ratio": round(sample_ratio, 6),
            "min": float(np.min(sampled)),
            "max": float(np.max(sampled)),
            "mean": float(np.mean(sampled)),
            "std": float(np.std(sampled)),
            "percentiles": {
                "p01": float(np.percentile(sampled, 1)),
                "p10": float(np.percentile(sampled, 10)),
                "p50": float(np.percentile(sampled, 50)),
                "p90": float(np.percentile(sampled, 90)),
                "p99": float(np.percentile(sampled, 99)),
            },
        }
        return stats

    def _generate_preview(
        self,
        dataset: pydicom.dataset.Dataset,
        desired_frame: int,
        max_preview_edge: int,
        original_filename: str,
    ) -> dict[str, Any]:
        try:
            pixel_array = dataset.pixel_array
        except Exception as exc:  # pylint: disable=broad-except
            return {"error": str(exc)}

        array = np.asarray(pixel_array)
        if array.size == 0:
            return {"error": "Pixel data is empty."}

        frame, actual_frame = self._select_frame(dataset, array, desired_frame)
        if frame is None:
            return {"error": "Requested frame index is out of range."}

        frame = np.asarray(frame)
        frame = np.squeeze(frame)
        original_shape = tuple(int(x) for x in frame.shape)

        mode = "L"
        if frame.ndim == 3:
            if frame.shape[0] in (3, 4) and frame.shape[-1] not in (3, 4):
                frame = np.moveaxis(frame, 0, -1)
            if frame.shape[-1] == 3:
                mode = "RGB"
            elif frame.shape[-1] == 4:
                mode = "RGBA"
            else:
                frame = frame[..., 0]
                mode = "L"
        elif frame.ndim != 2:
            return {"error": f"Unsupported pixel array shape {original_shape} for preview generation."}

        if mode == "L":
            preview_array = self._normalize_to_uint8(frame)
        else:
            preview_array = self._normalize_to_uint8(frame)

        try:
            image = Image.fromarray(preview_array, mode=mode)
        except Exception as exc:  # pylint: disable=broad-except
            return {"error": f"Failed to build preview image: {exc}"}

        resampling = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
        sanitized_edge = max(self.PREVIEW_MIN_EDGE, min(max_preview_edge, self.PREVIEW_MAX_EDGE))
        image.thumbnail((sanitized_edge, sanitized_edge), resampling)

        buffer = BytesIO()
        image.save(buffer, format="PNG")

        base_name = Path(original_filename).stem or "dicom_preview"
        filename = f"{base_name}_frame_{actual_frame}.png"

        return {
            "frame_index": int(actual_frame),
            "original_shape": original_shape,
            "preview_width": image.width,
            "preview_height": image.height,
            "mime_type": "image/png",
            "filename": filename,
            "blob": buffer.getvalue(),
            "note": "Preview is min-max normalized and downsampled to stay well under 20 MB.",
        }

    def _select_frame(
        self,
        dataset: pydicom.dataset.Dataset,
        array: np.ndarray,
        desired_frame: int,
    ) -> tuple[np.ndarray | None, int]:
        num_frames = getattr(dataset, "NumberOfFrames", 1)
        if array.ndim >= 4:
            frames = array.shape[0]
            index = max(0, min(int(desired_frame), frames - 1))
            return array[index], index
        if array.ndim == 3 and num_frames and num_frames > 1 and array.shape[0] == num_frames:
            frames = array.shape[0]
            index = max(0, min(int(desired_frame), frames - 1))
            return array[index], index
        return array, 0

    def _normalize_to_uint8(self, array: np.ndarray) -> np.ndarray:
        data = np.asarray(array)
        if data.dtype == np.uint8:
            return data
        data = data.astype(np.float32)
        min_value = float(np.min(data))
        max_value = float(np.max(data))
        if math.isclose(max_value, min_value):
            return np.zeros_like(data, dtype=np.uint8)
        data = (data - min_value) / (max_value - min_value)
        data = np.clip(data * 255.0, 0, 255).astype(np.uint8)
        return data

    def _build_summary(
        self,
        metadata: dict[str, Any],
        stats: dict[str, Any] | None,
        preview: dict[str, Any] | None,
        notes: list[str],
    ) -> str:
        file_meta = metadata["file"]
        patient = metadata.get("patient", {})
        study = metadata.get("study", {})
        series = metadata.get("series", {})
        image = metadata.get("image", {})

        lines = [
            f"File `{file_meta.get('filename', 'unknown')}` ({file_meta.get('size_megabytes', 0)} MB, "
            f"Transfer Syntax: {file_meta.get('transfer_syntax_name') or file_meta.get('transfer_syntax_uid') or 'unknown'})",
        ]

        patient_name = patient.get("Patient Name") or "unknown"
        patient_id = patient.get("Patient ID") or "unknown"
        lines.append(f"Patient: {patient_name} (ID: {patient_id})")

        modality = series.get("Modality") or image.get("Modality") or "unknown"
        study_desc = study.get("Study Description") or "unspecified study"
        study_date = study.get("Study Date") or "undated"
        lines.append(f"Study: {modality} on {study_date} — {study_desc}")

        dimensions = []
        if rows := image.get("Rows"):
            dimensions.append(f"{rows}")
        if cols := image.get("Columns"):
            if dimensions:
                dimensions[0] = f"{dimensions[0]} x {cols}"
            else:
                dimensions.append(str(cols))
        frames = file_meta.get("number_of_frames") or image.get("Number Of Frames")
        if dimensions:
            text = dimensions[0]
            if frames and frames > 1:
                text = f"{text} px, {frames} frames"
            else:
                text = f"{text} px"
            lines.append(f"Image size: {text}")

        if spacing := image.get("Pixel Spacing"):
            lines.append(f"Pixel spacing: {spacing}")

        if stats and "error" not in stats:
            lines.append(
                "Pixel stats (sampled)"
                f": min {stats['min']:.2f}, max {stats['max']:.2f}, mean {stats['mean']:.2f}, "
                f"std {stats['std']:.2f}"
            )

        if preview and "error" not in preview:
            lines.append(
                f"Preview frame {preview['frame_index']} -> {preview['preview_width']}x{preview['preview_height']} PNG "
                f"(see attached file {preview.get('filename', 'preview.png')})."
            )

        lines.extend(notes)

        if metadata.get("additional_tags"):
            tags_list = ", ".join(metadata["additional_tags"].keys())
            lines.append(f"Additional tags included: {tags_list}")

        lines.append("Large DICOM payloads are summarized so agents do not need to ingest the entire file.")
        return "\n".join(lines)

    def _format_value(self, value: Any) -> Any:
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

    def _parse_additional_tags(self, raw: Any) -> list[str]:
        if not raw:
            return []
        if isinstance(raw, str):
            parts = re.split(r"[,\\n]+", raw)
        elif isinstance(raw, list):
            parts = raw
        else:
            return []
        return [part.strip() for part in parts if part and part.strip()]

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

    def _as_int(self, value: Any, default: int = 0) -> int:
        if value is None:
            return default
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default
