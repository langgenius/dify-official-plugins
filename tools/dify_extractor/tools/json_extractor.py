"""JSON document extractor implementation."""

import json
from typing import Optional

from tools.extractor_base import BaseExtractor
from tools.helpers import detect_file_encodings
from tools.document import Document, ExtractorResult


class JSONExtractor(BaseExtractor):
    """Load JSON files.

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
        """Initialize with file bytes."""
        self._file_bytes = file_bytes
        self._file_name = file_name
        self._encoding = encoding
        self._autodetect_encoding = autodetect_encoding

    def extract(self) -> ExtractorResult:
        """Extract JSON content and format as markdown."""
        text = ""
        try:
            # Decode bytes to text
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
                raise RuntimeError(f"Error decoding {self._file_name}") from e
        except Exception as e:
            raise RuntimeError(f"Error loading {self._file_name}") from e

        # Parse JSON and format as markdown
        try:
            json_data = json.loads(text)
            # Pretty print JSON with proper indentation
            formatted_json = json.dumps(json_data, indent=2, ensure_ascii=False)
            
            # Format as markdown code block
            md_content = f"```json\n{formatted_json}\n```"
            
        except json.JSONDecodeError as e:
            # If JSON parsing fails, return the raw text with error info
            md_content = f"# JSON Parse Error\n\nError: {str(e)}\n\n## Raw Content\n\n```\n{text}\n```"
        except Exception as e:
            raise RuntimeError(f"Error parsing JSON in {self._file_name}") from e

        metadata = {"source": self._file_name, "type": "json"}
        return ExtractorResult(
            md_content=md_content, 
            documents=[Document(page_content=md_content, metadata=metadata)]
        )