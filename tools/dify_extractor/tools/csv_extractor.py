"""Strict CSV document extractor."""

import csv
from io import StringIO

from tools.document import Document, ExtractorResult
from tools.errors import ExtractionError
from tools.extractor_base import BaseExtractor
from tools.helpers import decode_text, render_markdown_table


class CSVExtractor(BaseExtractor):
    def extract(self) -> ExtractorResult:
        text = decode_text(self.context.file_bytes, self.context.file_name)
        reader = csv.reader(StringIO(text, newline=""), strict=True)
        try:
            raw_headers = next(reader)
        except StopIteration as exc:
            raise ExtractionError(f"File '{self.context.file_name}' contains no CSV rows.") from exc
        except csv.Error as exc:
            raise ExtractionError(
                f"File '{self.context.file_name}' contains invalid CSV data."
            ) from exc

        if not raw_headers or not any(header.strip() for header in raw_headers):
            raise ExtractionError(f"File '{self.context.file_name}' has no CSV header.")
        headers = [
            header.strip() or f"column_{index + 1}" for index, header in enumerate(raw_headers)
        ]

        rows: list[list[str]] = []
        documents: list[Document] = []
        try:
            for row_index, row in enumerate(reader):
                if not row or not any(cell.strip() for cell in row):
                    continue
                if len(row) != len(headers):
                    raise ExtractionError(
                        f"File '{self.context.file_name}' has {len(row)} columns on CSV row "
                        f"{reader.line_num}; expected {len(headers)}."
                    )
                rows.append(row)
                page_content = "; ".join(
                    f"{header}: {value.strip()}" for header, value in zip(headers, row, strict=True)
                )
                documents.append(
                    Document(
                        page_content=page_content,
                        metadata={"source": self.context.file_name, "row": row_index},
                    )
                )
        except csv.Error as exc:
            raise ExtractionError(
                f"File '{self.context.file_name}' contains invalid CSV data near row "
                f"{reader.line_num}."
            ) from exc

        return ExtractorResult(
            md_content=render_markdown_table(headers, rows),
            documents=documents,
        )
