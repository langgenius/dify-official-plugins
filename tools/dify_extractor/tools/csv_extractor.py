"""Abstract interface for document loader implementations."""

import csv
from typing import Optional

import pandas as pd
from tools.extractor_base import BaseExtractor
from tools.helpers import detect_file_encodings
from tools.document import Document, ExtractorResult
from io import BytesIO, TextIOWrapper


class CSVExtractor(BaseExtractor):
    """Load CSV files.


    Args:
        file_bytes: file bytes.
        file_name: file name.
        encoding: encoding.
        autodetect_encoding: autodetect encoding.
        csv_args: csv args.
    """

    def __init__(
        self,
        file_bytes: bytes,
        file_name: str,
        encoding: Optional[str] = None,
        autodetect_encoding: bool = False,
        csv_args: Optional[dict] = None,
    ):
        """Initialize with file path."""
        self._file_bytes = file_bytes
        self._file_name = file_name
        self._encoding = encoding if encoding else "utf-8"
        self._autodetect_encoding = autodetect_encoding
        self.csv_args = csv_args or {}

    def extract(self) -> ExtractorResult:
        """Load data into document objects."""
        csv_result = ExtractorResult(md_content="", documents=[])
        try:
            csvfile = TextIOWrapper(
                BytesIO(self._file_bytes), encoding=self._encoding, newline=""
            )
            markdown, docs = self._read_from_file(csvfile)
            csv_result.md_content = markdown
            csv_result.documents = docs
        except UnicodeDecodeError as e:
            if self._autodetect_encoding:
                detected_encodings = detect_file_encodings(self._file_bytes)
                for encoding in detected_encodings:
                    try:
                        csvfile = TextIOWrapper(
                            BytesIO(self._file_bytes),
                            encoding=encoding.encoding,
                            newline="",
                        )
                        markdown, docs = self._read_from_file(csvfile)
                        csv_result.md_content = markdown
                        csv_result.documents = docs
                        break
                    except UnicodeDecodeError:
                        continue
            else:
                raise RuntimeError(f"Error loading {self._file_name}") from e

        return csv_result

    def _read_from_file(self, csvfile) -> tuple[str, list[Document]]:
        docs = []
        markdown_content = ""
        try:
            # load csv file into pandas dataframe
            df = pd.read_csv(csvfile, on_bad_lines="skip", **self.csv_args)

            # create markdown table header
            headers = "| " + " | ".join(df.columns) + " |\n"
            separators = "| " + " | ".join(["---"] * len(df.columns)) + " |\n"
            markdown_content += headers + separators

            # create document objects and markdown content
            for i, row in df.iterrows():
                # strip whitespace from column values
                content = ";".join(
                    f"{col.strip()}: {str(row[col]).strip()}" for col in df.columns
                )
                metadata = {"source": self._file_name, "row": i}
                doc = Document(page_content=content, metadata=metadata)
                docs.append(doc)

                # markdown row
                markdown_row = (
                    "| "
                    + " | ".join(str(row[col]).strip() for col in df.columns)
                    + " |\n"
                )
                markdown_content += markdown_row

        except csv.Error as e:
            raise e

        return markdown_content, docs
