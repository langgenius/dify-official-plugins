"""Document loader helpers."""

import concurrent.futures
from pathlib import Path
from typing import NamedTuple, Optional, cast


class FileEncoding(NamedTuple):
    """A file encoding as the NamedTuple."""

    encoding: Optional[str]
    """The encoding of the file."""
    confidence: float
    """The confidence of the encoding."""
    language: Optional[str]
    """The language of the file."""


def detect_file_encodings(file_bytes: bytes, timeout: int = 5) -> list[FileEncoding]:
    """Try to detect the file encoding from bytes.

    Args:
        file_bytes: file bytes
        timeout: timeout in seconds
    """
    import chardet
    from io import BytesIO
    import csv

    def try_decode(data: bytes, encoding: str) -> bool:
        try:
            with BytesIO(data) as f:
                csv.Sniffer().sniff(f.read(1024).decode(encoding))
            return True
        except:
            return False

    def read_and_detect(data: bytes) -> list[dict]:
        raw_results = chardet.detect_all(data) or [chardet.detect(data)]

        valid_results = []
        for result in raw_results:
            if result["encoding"] and try_decode(data, result["encoding"]):
                valid_results.append(result)

        return valid_results or raw_results

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(read_and_detect, file_bytes)
        try:
            encodings = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError("Timeout reached while detecting encoding")

    if all(encoding["encoding"] is None for encoding in encodings):
        raise RuntimeError("Could not detect encoding")
    return [FileEncoding(**enc) for enc in encodings if enc["encoding"] is not None]
