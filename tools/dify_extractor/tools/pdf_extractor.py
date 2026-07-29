"""PDF document extractor."""

import logging
from io import BytesIO

import pypdfium2
import pypdfium2.raw as pdfium_c

from tools.document import Document, ExtractorResult
from tools.errors import ExtractionError
from tools.extractor_base import BaseExtractor

logger = logging.getLogger(__name__)


class PdfExtractor(BaseExtractor):
    IMAGE_FORMATS = [
        (b"\xff\xd8\xff", "jpg", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
        (b"\x00\x00\x00\x0cjP  \r\n\x87\n", "jp2", "image/jp2"),
        (b"GIF8", "gif", "image/gif"),
        (b"BM", "bmp", "image/bmp"),
        (b"II*\x00", "tiff", "image/tiff"),
        (b"MM\x00*", "tiff", "image/tiff"),
        (b"II+\x00", "tiff", "image/tiff"),
        (b"MM\x00+", "tiff", "image/tiff"),
    ]
    MAX_MAGIC_LENGTH = max(len(magic) for magic, _, _ in IMAGE_FORMATS)

    def extract(self) -> ExtractorResult:
        try:
            documents, image_files = self._parse()
        except pypdfium2.PdfiumError as exc:
            raise ExtractionError(
                f"File '{self.context.file_name}' is not a valid PDF file."
            ) from exc
        return ExtractorResult(
            md_content="\n\n".join(document.page_content for document in documents),
            documents=documents,
            img_list=image_files,
        )

    def _parse(self) -> tuple[list[Document], list]:
        documents: list[Document] = []
        image_files = []
        pdf_document = pypdfium2.PdfDocument(BytesIO(self.context.file_bytes), autoclose=True)
        try:
            for page_number in range(len(pdf_document)):
                page = pdf_document[page_number]
                try:
                    text_page = page.get_textpage()
                    try:
                        content = text_page.get_text_range()
                    finally:
                        text_page.close()

                    image_content, page_images = self._extract_images(page, page_number)
                    if image_content:
                        content = f"{content}\n{image_content}".strip()
                    image_files.extend(page_images)
                    documents.append(
                        Document(
                            page_content=content,
                            metadata={
                                "source": self.context.file_name,
                                "page": page_number,
                            },
                        )
                    )
                finally:
                    page.close()
        finally:
            pdf_document.close()
        return documents, image_files

    def _extract_images(self, page, page_number: int) -> tuple[str, list]:
        image_service = self.context.image_service
        if image_service is None:
            return "", []

        image_markdown: list[str] = []
        image_files = []
        try:
            image_objects = page.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_IMAGE,))
        except Exception as exc:
            logger.warning("Failed to enumerate images on PDF page %d: %s", page_number, exc)
            return "", []

        for image_index, image_object in enumerate(image_objects):
            try:
                image_buffer = BytesIO()
                image_object.extract(image_buffer, fb_format="png")
                image_bytes = image_buffer.getvalue()
                image_type = self._detect_image_type(image_bytes)
                if image_type is None:
                    continue
                extension, mime_type = image_type
                asset = image_service.upload_embedded(
                    image_bytes,
                    extension=extension,
                    mime_type=mime_type,
                    source=(
                        f"{self.context.file_name}:page-{page_number + 1}-image-{image_index + 1}"
                    ),
                )
                if asset:
                    image_markdown.append(asset.markdown)
                    image_files.append(asset.file)
            except Exception as exc:
                logger.warning("Failed to extract an image from PDF page %d: %s", page_number, exc)
        return "\n".join(image_markdown), image_files

    @classmethod
    def _detect_image_type(cls, image_bytes: bytes) -> tuple[str, str] | None:
        header = image_bytes[: cls.MAX_MAGIC_LENGTH]
        for magic, extension, mime_type in cls.IMAGE_FORMATS:
            if header.startswith(magic):
                return extension, mime_type
        return None
