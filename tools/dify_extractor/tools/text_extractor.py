"""Abstract interface for document loader implementations."""

from pathlib import Path
from typing import Optional

from tools.extractor_base import BaseExtractor
from tools.helpers import detect_file_encodings
from tools.document import Document, ExtractorResult


class TextExtractor(BaseExtractor):
    """Load text files.


    Args:
        file_bytes: file bytes.
        file_name: file name.
        encoding: encoding.
        autodetect_encoding: autodetect encoding.
    """

    def __init__(
        self,
        file_bytes: bytes,
        file_name: str,
        encoding: Optional[str] = None,
        autodetect_encoding: bool = False,
    ):
        """Initialize with file path."""
        self._file_bytes = file_bytes
        self._file_name = file_name
        self._encoding = encoding
        self._autodetect_encoding = autodetect_encoding

    def extract(self) -> ExtractorResult:
        """Load from file path."""
        text = ""
        try:
            text = self._file_bytes.decode(self._encoding if self._encoding else "utf-8")
        except UnicodeDecodeError as e:
            if self._autodetect_encoding:
                detected_encodings = detect_file_encodings(self._file_bytes)
                for encoding in detected_encodings:
                    try:
                        text = self._file_bytes.decode(encoding.encoding if encoding.encoding else "utf-8")
                        break
                    except UnicodeDecodeError:
                        continue
            else:
                raise RuntimeError(f"Error loading {self._file_name}") from e
        except Exception as e:
            raise RuntimeError(f"Error loading {self._file_name}") from e

        metadata = {"source": self._file_name}
        return ExtractorResult(
            md_content=text, documents=[Document(page_content=text, metadata=metadata)]
        )
