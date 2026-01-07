import io
import logging
import mimetypes
import uuid
from collections.abc import Iterator
from io import BytesIO

from dify_plugin import Tool

from tools.document import Document, ExtractorResult
from tools.extractor_base import BaseExtractor

import pypdfium2
import pypdfium2.raw as pdfium_c

logger = logging.getLogger(__name__)


class PdfExtractor(BaseExtractor):
    """Load pdf files.

    Args:
        tool: Tool instance
        file_bytes: file bytes
        file_name: file name.
    """

    # Magic bytes for image format detection: (magic_bytes, extension, mime_type)
    IMAGE_FORMATS = [
        (b"\xff\xd8\xff", "jpg", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
        (b"\x00\x00\x00\x0c\x6a\x50\x20\x20\x0d\x0a\x87\x0a", "jp2", "image/jp2"),
        (b"GIF8", "gif", "image/gif"),
        (b"BM", "bmp", "image/bmp"),
        (b"II*\x00", "tiff", "image/tiff"),
        (b"MM\x00*", "tiff", "image/tiff"),
        (b"II+\x00", "tiff", "image/tiff"),
        (b"MM\x00+", "tiff", "image/tiff"),
    ]
    MAX_MAGIC_LEN = max(len(m) for m, _, _ in IMAGE_FORMATS)

    def __init__(self, tool: Tool, file_bytes: bytes, file_name: str):
        self._file_bytes = file_bytes
        self._file_name = file_name
        self._tool = tool

    def extract(self) -> ExtractorResult:
        documents, img_list = self.parse()
        text_list = []
        for document in documents:
            text_list.append(document.page_content)
        text = "\n\n".join(text_list)

        return ExtractorResult(md_content=text, documents=documents, img_list=img_list)

    def parse(self) -> tuple[list[Document], list]:
        """Parse the bytes and return documents and images."""
        documents = []
        img_list = []
        with BytesIO(self._file_bytes) as file:
            pdf_reader = pypdfium2.PdfDocument(file, autoclose=True)
            try:
                for page_number, page in enumerate(pdf_reader):
                    text_page = page.get_textpage()
                    content = text_page.get_text_range()
                    text_page.close()

                    image_content, page_img_list = self._extract_images(page)
                    if image_content:
                        content += "\n" + image_content
                    img_list.extend(page_img_list)

                    page.close()
                    metadata = {"source": self._file_name, "page": page_number}
                    documents.append(Document(page_content=content, metadata=metadata))
            finally:
                pdf_reader.close()
        return documents, img_list

    def _extract_images(self, page) -> tuple[str, list]:
        """
        Extract images from a PDF page, save them to storage,
        and return markdown image links.

        Args:
            page: pypdfium2 page object.

        Returns:
            Markdown string containing links to the extracted images.
        """
        image_content = []
        img_list = []

        try:
            image_objects = page.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_IMAGE,))
            for obj in image_objects:
                try:
                    # Extract image bytes
                    img_byte_arr = io.BytesIO()
                    # Extract DCTDecode (JPEG) and JPXDecode (JPEG 2000) images directly
                    # Fallback to png for other formats
                    obj.extract(img_byte_arr, fb_format="png")
                    img_bytes = img_byte_arr.getvalue()

                    if not img_bytes:
                        continue

                    header = img_bytes[: self.MAX_MAGIC_LEN]
                    image_ext = None
                    mime_type = None
                    for magic, ext, mime in self.IMAGE_FORMATS:
                        if header.startswith(magic):
                            image_ext = ext
                            mime_type = mime
                            break

                    if not image_ext or not mime_type:
                        continue

                    file_uuid = str(uuid.uuid4())
                    file_name = file_uuid + "." + image_ext

                    file_res = self._tool.session.file.upload(
                        file_name, img_bytes, mime_type
                    )
                    image_content.append(f"![image]({file_res.preview_url})")
                    img_list.append(file_res)
                except Exception as e:
                    logger.warning("Failed to extract image from PDF: %s", e)
                    continue
        except Exception as e:
            logger.warning("Failed to get objects from PDF page: %s", e)

        return "\n".join(image_content), img_list
