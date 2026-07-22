"""Shared decoding, Markdown, and archive-safety helpers."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from io import BytesIO
from zipfile import BadZipFile, ZipFile

import chardet

from tools.errors import ExtractionError

MAX_ARCHIVE_ENTRIES = 10_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 1_000

_BAD_OFFICE_FORMAT_HINTS = {
    ".docx": "old binary .doc instead of .docx",
    ".xlsx": "old binary .xls instead of .xlsx",
    ".pptx": "old binary .ppt instead of .pptx",
}


def decode_text(file_bytes: bytes, file_name: str, preferred_encoding: str | None = None) -> str:
    """Decode text strictly, trying UTF-8/BOM handling before detected encodings."""
    if not file_bytes:
        raise ExtractionError(f"File '{file_name}' is empty.")

    candidates = [preferred_encoding, "utf-8-sig"]
    detected = chardet.detect_all(file_bytes) or [chardet.detect(file_bytes)]
    candidates.extend(result.get("encoding") for result in detected)

    attempted: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        normalized = candidate.casefold()
        if normalized in attempted:
            continue
        attempted.add(normalized)
        try:
            return file_bytes.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue

    raise ExtractionError(f"File '{file_name}' could not be decoded as text.")


def escape_markdown_cell(value: object) -> str:
    """Escape a value for use inside a GitHub-style Markdown table."""
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\\", "\\\\").replace("|", "\\|")
    return text.replace("\r\n", "<br>").replace("\r", "<br>").replace("\n", "<br>")


def render_markdown_table(headers: Sequence[object], rows: Iterable[Sequence[object]]) -> str:
    """Render a consistently escaped Markdown table."""
    escaped_headers = [escape_markdown_cell(header) for header in headers]
    lines = [
        "| " + " | ".join(escaped_headers) + " |",
        "| " + " | ".join("---" for _ in escaped_headers) + " |",
    ]
    lines.extend(
        "| " + " | ".join(escape_markdown_cell(value) for value in row) + " |" for row in rows
    )
    return "\n".join(lines) + "\n"


def validate_office_archive(file_bytes: bytes, file_name: str, extension: str) -> None:
    """Reject corrupt or suspiciously expanded OOXML archives before parsing."""
    try:
        with ZipFile(BytesIO(file_bytes)) as archive:
            entries = archive.infolist()
    except BadZipFile as exc:
        hint = _BAD_OFFICE_FORMAT_HINTS.get(extension)
        suffix = f" (for example, {hint})" if hint else ""
        raise ExtractionError(
            f"File '{file_name}' is not a valid {extension} file. "
            f"It may be corrupted or use an incompatible format{suffix}."
        ) from exc

    if len(entries) > MAX_ARCHIVE_ENTRIES:
        raise ExtractionError(
            f"File '{file_name}' contains too many archive entries "
            f"(maximum {MAX_ARCHIVE_ENTRIES:,})."
        )

    total_uncompressed = sum(entry.file_size for entry in entries)
    total_compressed = sum(entry.compress_size for entry in entries)
    if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
        raise ExtractionError(f"File '{file_name}' expands beyond the 200 MiB safety limit.")

    ratios = [entry.file_size / max(entry.compress_size, 1) for entry in entries if entry.file_size]
    total_ratio = total_uncompressed / max(total_compressed, 1)
    if total_ratio > MAX_ARCHIVE_COMPRESSION_RATIO or any(
        ratio > MAX_ARCHIVE_COMPRESSION_RATIO for ratio in ratios
    ):
        raise ExtractionError(
            f"File '{file_name}' exceeds the archive compression-ratio safety limit."
        )

    if not math.isfinite(total_ratio):
        raise ExtractionError(f"File '{file_name}' has invalid archive metadata.")
