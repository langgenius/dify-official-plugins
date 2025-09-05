"""YAML document extractor implementation."""

import yaml
from typing import Optional

from tools.extractor_base import BaseExtractor
from tools.helpers import detect_file_encodings
from tools.document import Document, ExtractorResult


class YAMLExtractor(BaseExtractor):
    """Load YAML files.

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
        """Extract YAML content and format as markdown."""
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

        # Parse YAML and format as markdown
        try:
            yaml_data = yaml.safe_load(text)
            # Convert back to YAML with proper formatting
            formatted_yaml = yaml.dump(yaml_data, default_flow_style=False, allow_unicode=True, indent=2)
            
            # Format as markdown code block
            md_content = f"```yaml\n{formatted_yaml}```"
            
        except yaml.YAMLError as e:
            # If YAML parsing fails, return the raw text with error info
            md_content = f"# YAML Parse Error\n\nError: {str(e)}\n\n## Raw Content\n\n```\n{text}\n```"
        except Exception as e:
            raise RuntimeError(f"Error parsing YAML in {self._file_name}") from e

        metadata = {"source": self._file_name, "type": "yaml"}
        return ExtractorResult(
            md_content=md_content, 
            documents=[Document(page_content=md_content, metadata=metadata)]
        )