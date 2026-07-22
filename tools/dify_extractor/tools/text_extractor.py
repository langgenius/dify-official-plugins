"""Plain-text document extractor."""

from tools.document import Document, ExtractorResult
from tools.extractor_base import BaseExtractor
from tools.helpers import decode_text


class TextExtractor(BaseExtractor):
    def extract(self) -> ExtractorResult:
        text = decode_text(self.context.file_bytes, self.context.file_name)
        metadata = {"source": self.context.file_name}
        return ExtractorResult(
            md_content=text,
            documents=[Document(page_content=text, metadata=metadata)],
        )
