"""JSON document extractor."""

import json

from tools.document import Document, ExtractorResult
from tools.errors import ExtractionError
from tools.extractor_base import BaseExtractor
from tools.helpers import decode_text


class JSONExtractor(BaseExtractor):
    def extract(self) -> ExtractorResult:
        text = decode_text(self.context.file_bytes, self.context.file_name)
        try:
            json_data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ExtractionError(
                f"File '{self.context.file_name}' contains invalid JSON at "
                f"line {exc.lineno}, column {exc.colno}."
            ) from exc

        formatted_json = json.dumps(json_data, indent=2, ensure_ascii=False)
        md_content = f"```json\n{formatted_json}\n```"
        return ExtractorResult(
            md_content=md_content,
            documents=[
                Document(
                    page_content=md_content,
                    metadata={"source": self.context.file_name, "type": "json"},
                )
            ],
        )
