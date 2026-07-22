import logging
import os
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.context import ExtractionContext
from tools.csv_extractor import CSVExtractor
from tools.document import ExtractorResult
from tools.errors import ExtractionError
from tools.excel_extractor import ExcelExtractor
from tools.extractor_base import BaseExtractor
from tools.helpers import validate_office_archive
from tools.html_extractor import HtmlExtractor
from tools.image_assets import ImageAssetService
from tools.json_extractor import JSONExtractor
from tools.markdown_extractor import MarkdownExtractor
from tools.pdf_extractor import PdfExtractor
from tools.pptx_extractor import PPTXExtractor
from tools.text_extractor import TextExtractor
from tools.word_extractor import WordExtractor
from tools.yaml_extractor import YAMLExtractor

logger = logging.getLogger(__name__)

_EXTRACTORS: dict[str, type[BaseExtractor]] = {
    ".csv": CSVExtractor,
    ".docx": WordExtractor,
    ".htm": HtmlExtractor,
    ".html": HtmlExtractor,
    ".json": JSONExtractor,
    ".md": MarkdownExtractor,
    ".markdown": MarkdownExtractor,
    ".mdx": MarkdownExtractor,
    ".pdf": PdfExtractor,
    ".pptx": PPTXExtractor,
    ".xls": ExcelExtractor,
    ".xlsx": ExcelExtractor,
    ".yaml": YAMLExtractor,
    ".yml": YAMLExtractor,
}
_PLAIN_TEXT_EXTENSIONS = {
    ".cfg",
    ".conf",
    ".ini",
    ".log",
    ".rst",
    ".text",
    ".txt",
    ".xml",
}
_TEXT_MIME_TYPES = {
    "application/toml",
    "application/xml",
    "application/x-ndjson",
    "application/x-yaml",
}
_MIME_EXTENSIONS = {
    "application/json": ".json",
    "application/pdf": ".pdf",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/x-yaml": ".yaml",
    "application/yaml": ".yaml",
    "text/csv": ".csv",
    "text/html": ".html",
    "text/markdown": ".md",
    "text/yaml": ".yaml",
}
_OOXML_EXTENSIONS = {".docx", ".pptx", ".xlsx"}


class DifyExtractorTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        file = tool_parameters.get("file")
        if file is None:
            yield self.create_text_message("A file is required.")
            return

        file_name, extension, mime_type = self._resolve_file_identity(file)
        try:
            file_bytes = file.blob
        except Exception:
            logger.exception("Failed to read file '%s'", file_name)
            yield self.create_text_message(
                f"Failed to read file '{file_name}'. Check that Dify's FILES_URL is "
                "reachable from the plugin runtime."
            )
            return

        if not isinstance(file_bytes, (bytes, bytearray)) or not file_bytes:
            yield self.create_text_message(f"File '{file_name}' is empty.")
            return

        try:
            extractor_class, resolved_extension = self._resolve_extractor(
                extension,
                mime_type,
            )
            content = bytes(file_bytes)
            if resolved_extension in _OOXML_EXTENSIONS:
                validate_office_archive(content, file_name, resolved_extension)

            context = ExtractionContext(
                file_bytes=content,
                file_name=file_name,
                file_extension=resolved_extension,
                mime_type=mime_type,
                image_service=ImageAssetService(self, logger),
            )
            result = extractor_class(context).extract()
            self._validate_result(result, file_name)
        except ExtractionError as exc:
            logger.warning("Could not extract '%s': %s", file_name, exc)
            yield self.create_text_message(str(exc))
            return
        except Exception:
            logger.exception("Unexpected failure while extracting '%s'", file_name)
            yield self.create_text_message(
                f"Failed to extract '{file_name}'. See the plugin logs for details."
            )
            return

        if result.img_list:
            yield self.create_variable_message("images", result.img_list)
        yield self.create_text_message(result.md_content)
        yield self.create_variable_message("documents", result.documents)

    @staticmethod
    def _resolve_file_identity(file: Any) -> tuple[str, str, str | None]:
        raw_name = getattr(file, "filename", None)
        supplied_extension = DifyExtractorTool._normalize_extension(
            getattr(file, "extension", None)
        )
        name_extension = DifyExtractorTool._normalize_extension(
            os.path.splitext(raw_name)[1] if raw_name else None
        )
        mime_type = (getattr(file, "mime_type", None) or "").split(";", 1)[0].strip().casefold()
        mime_extension = _MIME_EXTENSIONS.get(mime_type)

        known_extensions = set(_EXTRACTORS) | _PLAIN_TEXT_EXTENSIONS
        extension = next(
            (
                candidate
                for candidate in (name_extension, supplied_extension, mime_extension)
                if candidate in known_extensions
            ),
            name_extension or supplied_extension or mime_extension or "",
        )
        file_name = str(raw_name) if raw_name else f"uploaded{extension or '.txt'}"
        return file_name, extension, mime_type or None

    @staticmethod
    def _resolve_extractor(
        extension: str,
        mime_type: str | None,
    ) -> tuple[type[BaseExtractor], str]:
        if extractor := _EXTRACTORS.get(extension):
            return extractor, extension
        if extension in _PLAIN_TEXT_EXTENSIONS:
            return TextExtractor, extension
        if mime_type and (mime_type.startswith("text/") or mime_type in _TEXT_MIME_TYPES):
            return TextExtractor, extension or ".txt"

        display_extension = extension or mime_type or "unknown"
        raise ExtractionError(
            f"Unsupported file format '{display_extension}'. Supported formats are PDF, DOCX, "
            "PPTX, XLS/XLSX, Markdown, HTML, CSV, JSON, YAML, and plain text."
        )

    @staticmethod
    def _normalize_extension(extension: str | None) -> str:
        if not extension:
            return ""
        normalized = extension.strip().casefold()
        return normalized if normalized.startswith(".") else f".{normalized}"

    @staticmethod
    def _validate_result(result: ExtractorResult, file_name: str) -> None:
        if not result.md_content.strip() or not any(
            document.page_content.strip() for document in result.documents
        ):
            raise ExtractionError(f"File '{file_name}' contains no extractable content.")
