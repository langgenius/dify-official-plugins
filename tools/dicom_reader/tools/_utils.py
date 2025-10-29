from __future__ import annotations

import math
import re
from datetime import date, datetime, time
from decimal import Decimal
from io import BytesIO
from typing import Any, Iterable

import numpy as np
import pydicom
from PIL import Image
from pydicom.datadict import tag_for_keyword
from pydicom.errors import InvalidDicomError
from pydicom.multival import MultiValue
from pydicom.sequence import Sequence
from pydicom.tag import BaseTag, Tag
from pydicom.uid import UID

try:
    from pydicom.valuerep import PersonNameBase
except ImportError:  # pragma: no cover
    from pydicom.valuerep import PersonName as PersonNameBase


# Preview tuning constants
PREVIEW_MIN_EDGE = 32
PREVIEW_MAX_EDGE = 1024
MAX_BLOB_BYTES = 8 * 1024 * 1024  # ~8 MB soft cap


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return default


def as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def sanitize_edge(edge: int) -> int:
    return max(PREVIEW_MIN_EDGE, min(int(edge), PREVIEW_MAX_EDGE))


def ensure_hw_or_hwc(array: np.ndarray) -> np.ndarray:
    arr = np.asarray(array)
    arr = np.squeeze(arr)
    if arr.ndim == 2:
        return arr
    if arr.ndim == 3:
        # move channels to last if likely first
        if arr.shape[0] in (3, 4) and arr.shape[-1] not in (3, 4):
            arr = np.moveaxis(arr, 0, -1)
        # ensure last dim is 1/3/4
        if arr.shape[-1] in (3, 4):
            return arr
        return arr[..., 0]
    # fallback to 2D
    return np.squeeze(arr)


def to_uint8_minmax(array: np.ndarray) -> np.ndarray:
    data = np.asarray(array)
    if data.dtype == np.uint8:
        return data
    data = data.astype(np.float32)
    vmin = float(np.min(data))
    vmax = float(np.max(data))
    if math.isclose(vmax, vmin):
        return np.zeros_like(data, dtype=np.uint8)
    data = (data - vmin) / (vmax - vmin)
    return np.clip(data * 255.0, 0, 255).astype(np.uint8)


def to_pil_image(array: np.ndarray) -> tuple[Image.Image, str]:
    arr = ensure_hw_or_hwc(array)
    if arr.ndim == 2:
        mode = "L"
        img = Image.fromarray(to_uint8_minmax(arr), mode=mode)
        return img, mode
    # RGB/RGBA
    c = arr.shape[-1]
    if c == 3:
        mode = "RGB"
    elif c == 4:
        mode = "RGBA"
    else:
        arr = arr[..., 0]
        mode = "L"
    img = Image.fromarray(to_uint8_minmax(arr), mode=mode)
    return img, mode


def make_preview_png_bytes(array: np.ndarray, max_edge: int) -> tuple[bytes, int, int]:
    img, _ = to_pil_image(array)
    resampling = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
    current_edge = sanitize_edge(max_edge)
    blob = None
    width = height = None
    while current_edge >= PREVIEW_MIN_EDGE:
        trial = img.copy()
        trial.thumbnail((current_edge, current_edge), resampling)
        buf = BytesIO()
        try:
            trial.save(buf, format="PNG", optimize=True)
        except Exception:  # pylint: disable=broad-except
            trial.save(buf, format="PNG")
        data = buf.getvalue()
        if len(data) <= MAX_BLOB_BYTES or current_edge == PREVIEW_MIN_EDGE:
            blob = data
            width, height = trial.width, trial.height
            break
        current_edge = max(PREVIEW_MIN_EDGE, int(current_edge * 0.75))
    return blob or b"", int(width or img.width), int(height or img.height)


def select_frame(dataset: pydicom.dataset.Dataset, array: np.ndarray, desired_frame: int) -> tuple[np.ndarray, int]:
    num_frames = int(getattr(dataset, "NumberOfFrames", 1) or 1)
    arr = np.asarray(array)
    if arr.ndim >= 4:
        frames = arr.shape[0]
        index = max(0, min(int(desired_frame), frames - 1))
        return arr[index], index
    if arr.ndim == 3 and num_frames > 1 and arr.shape[0] == num_frames:
        frames = arr.shape[0]
        index = max(0, min(int(desired_frame), frames - 1))
        return arr[index], index
    return arr, 0


def read_dicom_from_fileobj(file_obj: Any, need_pixels: bool) -> tuple[pydicom.dataset.Dataset | None, str, int, str | None]:
    blob = getattr(file_obj, "blob", None)
    if blob is None:
        return None, "dicom_file.dcm", 0, "Unable to read the uploaded file."
    filename = getattr(file_obj, "filename", "dicom_file.dcm")
    try:
        ds = pydicom.dcmread(BytesIO(blob), stop_before_pixels=not need_pixels, force=True)
    except InvalidDicomError as exc:
        return None, filename, len(blob), f"The provided file is not a valid DICOM dataset: {exc}"
    except Exception as exc:  # pylint: disable=broad-except
        return None, filename, len(blob), f"Failed to parse DICOM file: {exc}"
    return ds, filename, len(blob), None


# Metadata helpers -----------------------------------------------------------

def display_name(attr_name: str) -> str:
    words = re.findall(r"[A-Z]+[a-z]*|[a-z]+|[0-9]+", attr_name)
    return " ".join(word.capitalize() for word in words)


def format_value(value: Any) -> Any:
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
        return [format_value(item) for item in value[:16]]
    text = str(value)
    return text if len(text) <= 200 else f"{text[:197]}..."


def collect_named_fields(dataset: pydicom.dataset.Dataset, fields: Iterable[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in fields:
        if not hasattr(dataset, name):
            continue
        value = getattr(dataset, name, None)
        if value is None:
            continue
        formatted = format_value(value)
        if formatted is not None and formatted != "":
            result[display_name(name)] = formatted
    return result


def parse_additional_tags(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        parts = re.split(r"[,\n]+", raw)
    elif isinstance(raw, list):
        parts = raw
    else:
        return []
    return [part.strip() for part in parts if part and part.strip()]


def parse_tag_keyword(lookup: str) -> BaseTag | None:
    # Hex like 0018,5100 or (0018,5100)
    hex_match = re.fullmatch(r"\(?\s*([0-9A-Fa-f]{4})[,\s]+([0-9A-Fa-f]{4})\s*\)?", lookup)
    if hex_match:
        group = int(hex_match.group(1), 16)
        element = int(hex_match.group(2), 16)
        return Tag(group, element)
    cleaned = re.sub(r"[^0-9A-Za-z_]", "", lookup)
    candidates = {cleaned, cleaned.lower(), cleaned.upper(), cleaned.capitalize()}
    for candidate in candidates:
        try:
            tag = tag_for_keyword(candidate)
            if tag:
                return Tag(tag)
        except Exception:  # pylint: disable=broad-except
            continue
    return None


def collect_additional_tags(dataset: pydicom.dataset.Dataset, requested_tags: list[str]) -> dict[str, Any]:
    collected: dict[str, Any] = {}
    for raw_tag in requested_tags:
        lookup = raw_tag.strip()
        if not lookup:
            continue
        tag = parse_tag_keyword(lookup)
        if tag is None or tag not in dataset:
            continue
        data_element = dataset[tag]
        value = format_value(data_element.value)
        if value is not None:
            collected[data_element.name] = value
    return collected


def file_stats(dataset: pydicom.dataset.Dataset, size_bytes: int, filename: str) -> dict[str, Any]:
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

