from collections.abc import Iterator
from io import BytesIO
from tools.extractor_base import BaseExtractor
from tools.document import Document, ExtractorResult


class PdfExtractor(BaseExtractor):
    """Load pdf files.


    Args:
        file_bytes: file bytes
        file_name: file name.
    """

    def __init__(self, file_bytes: bytes, file_name: str):
        self._file_bytes = file_bytes
        self._file_name = file_name

    def extract(self) -> ExtractorResult:
        documents = list(self.parse())
        text_list = []
        for document in documents:
            text_list.append(document.page_content)
        text = "\n\n".join(text_list)

        return ExtractorResult(md_content=text, documents=documents)

    def parse(self) -> Iterator[Document]:
        """Lazily parse the bytes."""
        import pypdfium2  # type: ignore

        with BytesIO(self._file_bytes) as file:
            pdf_reader = pypdfium2.PdfDocument(file, autoclose=True)
            try:
                for page_number, page in enumerate(pdf_reader):
                    text_page = page.get_textpage()
                    content = text_page.get_text_range()
                    text_page.close()
                    page.close()
                    metadata = {"source": self._file_name, "page": page_number}
                    yield Document(page_content=content, metadata=metadata)
            finally:
                pdf_reader.close()
