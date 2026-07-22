"""HTML document extractor."""

from bs4 import BeautifulSoup

from tools.document import Document, ExtractorResult
from tools.extractor_base import BaseExtractor
from tools.helpers import decode_text


class HtmlExtractor(BaseExtractor):
    def extract(self) -> ExtractorResult:
        html = decode_text(self.context.file_bytes, self.context.file_name)
        soup = BeautifulSoup(html, "html.parser")
        for element in soup(["script", "style", "noscript"]):
            element.decompose()
        text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
        return ExtractorResult(
            md_content=text,
            documents=[
                Document(
                    page_content=text,
                    metadata={"source": self.context.file_name},
                )
            ],
        )
