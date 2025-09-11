"""Abstract interface for document loader implementations."""

from bs4 import BeautifulSoup  # type: ignore

from tools.extractor_base import BaseExtractor
from tools.document import Document, ExtractorResult


class HtmlExtractor(BaseExtractor):
    """
    Load html files.

    Args:
        file_bytes: HTML content in bytes format.
        file_name: file name.
    """

    def __init__(self, file_bytes: bytes, file_name: str):
        """Initialize with file bytes."""
        self._file_bytes = file_bytes
        self._file_name = file_name

    def extract(self) -> ExtractorResult:
        text = self._load_as_text()
        return ExtractorResult(
            md_content=text,
            documents=[
                Document(page_content=text, metadata={"source": self._file_name})
            ],
        )

    def _load_as_text(self) -> str:
        from io import BytesIO

        text: str = ""
        with BytesIO(self._file_bytes) as fp:
            soup = BeautifulSoup(fp, "html.parser")
            text = soup.get_text()
            text = text.strip() if text else ""
        return text
