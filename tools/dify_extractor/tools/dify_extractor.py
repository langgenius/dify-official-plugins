import os
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.csv_extractor import CSVExtractor
from tools.excel_extractor import ExcelExtractor
from tools.html_extractor import HtmlExtractor
from tools.json_extractor import JSONExtractor
from tools.markdown_extractor import MarkdownExtractor
from tools.pdf_extractor import PdfExtractor
from tools.text_extractor import TextExtractor
from tools.word_extractor import WordExtractor
from tools.pptx_extractor import PPTXExtractor
from tools.yaml_extractor import YAMLExtractor


class DifyExtractorTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        file = tool_parameters.get("file")
        if not file:
            raise ValueError("file is required")
        file_name = file.filename
        file_extension = os.path.splitext(file_name)[-1].lower()
        file_bytes = file.blob
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
        extractor_result = extractor.extract()
        if extractor_result.img_list:
            yield self.create_variable_message("images", extractor_result.img_list)
        yield self.create_text_message(extractor_result.md_content)
        yield self.create_variable_message("documents", extractor_result.documents)
