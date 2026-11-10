"""Turn the different MinerU result payloads into one ``ParsedDocument``."""

import base64
import io
import json
import logging
import mimetypes
import os
import zipfile
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
EXTRA_FORMAT_FILES = {
    "html": ("text/html", ".html"),
    "latex": ("application/x-tex", ".tex"),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
}


@dataclass
class ResultFile:
    name: str
    data: bytes
    mime_type: str


@dataclass
class ParsedDocument:
    markdown: str = ""
    # Each entry becomes one json message, in order.
    json_messages: list[dict[str, Any]] = field(default_factory=list)
    images: list[ResultFile] = field(default_factory=list)
    extra_files: list[ResultFile] = field(default_factory=list)


def image_mime_type(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "image/jpeg"


def _open_zip(data: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ValueError(f"MinerU returned an invalid zip file: {e}") from e


def from_cloud_zip(data: bytes) -> ParsedDocument:
    """Official API zip: full.md, *_content_list.json, layout.json, images/, extra formats."""
    doc = ParsedDocument()
    content_list: list[Any] = []
    with _open_zip(data) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename.lower()
            base_name = os.path.basename(info.filename)
            try:
                raw = archive.read(info)
                if name.startswith("images/") and name.endswith(IMAGE_EXTENSIONS):
                    doc.images.append(ResultFile(base_name, raw, image_mime_type(base_name)))
                elif name.endswith(".md"):
                    doc.markdown = raw.decode("utf-8")
                elif name.endswith(".json") and name != "layout.json":
                    content_list.append(json.loads(raw.decode("utf-8")))
                elif name.endswith(".html"):
                    doc.extra_files.append(ResultFile(base_name, raw, "text/html"))
                elif name.endswith(".docx"):
                    doc.extra_files.append(ResultFile(base_name, raw, EXTRA_FORMAT_FILES["docx"][0]))
                elif name.endswith(".tex"):
                    doc.extra_files.append(ResultFile(base_name, raw, "application/x-tex"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                logger.error(f"Failed to read {info.filename} from the MinerU result zip: {e}")
    doc.json_messages.append({"content_list": content_list})
    return doc


def from_v1_zip(data: bytes, extra_files: dict[str, bytes], source_name: str) -> ParsedDocument:
    """MinerU 4.x zip: markdown.md, structured_content.json, middle_json.json, images/."""
    doc = ParsedDocument()
    structured_content: Any = None
    with _open_zip(data) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename
            base_name = os.path.basename(name)
            lower = base_name.lower()
            try:
                if "/images/" in f"/{name}" and lower.endswith(IMAGE_EXTENSIONS):
                    doc.images.append(ResultFile(base_name, archive.read(info), image_mime_type(base_name)))
                elif lower.endswith(".md") and not doc.markdown:
                    doc.markdown = archive.read(info).decode("utf-8")
                elif lower == "structured_content.json":
                    structured_content = json.loads(archive.read(info).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                logger.error(f"Failed to read {name} from the MinerU result zip: {e}")
    doc.json_messages.append({"structured_content": structured_content})
    stem = os.path.splitext(source_name)[0] or "result"
    for fmt, payload in extra_files.items():
        mime_type, extension = EXTRA_FORMAT_FILES[fmt]
        doc.extra_files.append(ResultFile(f"{stem}{extension}", payload, mime_type))
    return doc


def _decode_data_uri_images(images: dict[str, str]) -> list[ResultFile]:
    files = []
    for name, encoded in (images or {}).items():
        try:
            payload = encoded.split(",", 1)[1] if "," in encoded else encoded
            files.append(ResultFile(name, base64.b64decode(payload), image_mime_type(name)))
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to decode image {name} from MinerU: {e}")
    return files


def from_legacy_response(response: dict[str, Any], version: str) -> ParsedDocument:
    """MinerU 1.x (``version="v1"``) or 2.x/3.x (``"v2"``) ``/file_parse`` JSON."""
    if version == "v1":
        doc = ParsedDocument(markdown=response.get("md_content", ""))
        doc.images = _decode_data_uri_images(response.get("images") or {})
        doc.json_messages.append({"content_list": response.get("content_list", [])})
        return doc

    results = response.get("results") or {}
    if not results:
        raise ValueError(f"MinerU returned no results: {json.dumps(response)[:500]}")
    # One file is uploaded per call, so there is exactly one result.
    file_name, result = next(iter(results.items()))
    doc = ParsedDocument(markdown=result.get("md_content") or "")
    doc.images = _decode_data_uri_images(result.get("images") or {})
    content_list = result.get("content_list")
    if isinstance(content_list, str):
        try:
            content_list = json.loads(content_list)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse content_list JSON: {e}")
            content_list = None
    result_item: dict[str, Any] = {"filename": file_name}
    if content_list is not None:
        doc.json_messages.append({"content_list": content_list})
        result_item["content_list"] = content_list
    if doc.markdown:
        result_item["md_content"] = doc.markdown
    doc.json_messages.append({"_result": result_item})
    return doc
