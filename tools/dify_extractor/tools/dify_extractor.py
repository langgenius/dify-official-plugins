import logging
import os
from collections.abc import Generator
from typing import Any
from zipfile import BadZipFile

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
        if not file:
            raise ValueError("file is required")
        file_name = file.filename
        file_extension = os.path.splitext(file_name)[-1].lower()

        try:
            file_bytes = file.blob
        except Exception as e:
            yield self.create_text_message(f"Failed to read file '{file_name}': {e}")
            return

        if file_extension in {".xlsx", ".xls"}:
            extractor = ExcelExtractor(file_bytes, file_name)
        elif file_extension == ".pdf":
            extractor = PdfExtractor(self, file_bytes, file_name)
        elif file_extension in {".md", ".markdown", ".mdx"}:
            extractor = MarkdownExtractor(file_bytes, file_name, tool=self, autodetect_encoding=True)
        elif file_extension in {".htm", ".html"}:
            extractor = HtmlExtractor(file_bytes, file_name)
        elif file_extension == ".docx":
            extractor = WordExtractor(self, file_bytes, file_name)
        elif file_extension == ".pptx":
            extractor = PPTXExtractor(self, file_bytes, file_name)
        elif file_extension == ".csv":
            extractor = CSVExtractor(file_bytes, file_name, autodetect_encoding=True)
        elif file_extension == ".json":
            extractor = JSONExtractor(file_bytes, file_name, autodetect_encoding=True)
        elif file_extension in {".yaml", ".yml"}:
            extractor = YAMLExtractor(file_bytes, file_name, autodetect_encoding=True)
        else:
            # txt
            extractor = TextExtractor(file_bytes, file_name, autodetect_encoding=True)

        try:
            extractor_result = extractor.extract()
        except BadZipFile:
            yield self.create_text_message(
                f"File '{file_name}' is not a valid {file_extension} file. "
                f"It may be corrupted or in an incompatible format (e.g., old binary .doc instead of .docx)."
            )
            return
        except Exception as e:
            yield self.create_text_message(f"Failed to extract '{file_name}': {e}")
            return

        if extractor_result.img_list:
            yield self.create_variable_message("images", extractor_result.img_list)
        yield self.create_text_message(extractor_result.md_content)
        yield self.create_variable_message("documents", extractor_result.documents)
