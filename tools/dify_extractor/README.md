# Dify Extractor

Dify Extractor converts uploaded documents into Markdown plus structured document records for
RAG pipelines and workflows.

## Supported formats

- PDF (`.pdf`)
- Microsoft Word (`.docx`)
- Microsoft PowerPoint (`.pptx`)
- Microsoft Excel (`.xls`, `.xlsx`)
- Markdown (`.md`, `.markdown`, `.mdx`)
- HTML (`.htm`, `.html`)
- CSV (`.csv`)
- JSON (`.json`)
- YAML (`.yaml`, `.yml`)
- Plain-text formats such as `.txt`, `.log`, `.rst`, `.ini`, `.cfg`, `.conf`, and `.xml`

Text MIME types are also accepted when a file has no recognized extension. Unsupported binary
formats return a clear error instead of being decoded as text.

## Outputs

- The text output contains the complete extracted Markdown.
- `documents` contains format-appropriate records: rows for CSV/Excel, pages for PDF, sections for
  Markdown, and a whole-file record for the other formats.
- `images` is emitted when embedded or referenced images are successfully uploaded to Dify.

Malformed, empty, undecodable, or resource-limit-breaking files return one error message and do
not emit partial document variables.

## Image and archive safeguards

Remote Markdown and DOCX images are imported on a best-effort basis. Only HTTP(S) URLs are used,
with a 30-second request timeout, a maximum of 20 images, a 15 MiB per-image limit, and a 100 MiB
cumulative limit. A failed image download or upload does not discard otherwise extractable text.

ZIP-based Office files are rejected before parsing if they contain more than 10,000 entries,
expand beyond 200 MiB, or exceed a 1,000:1 compression ratio.

## Development

The plugin targets Python 3.12 and uses `uv` for dependency management.

```bash
uv sync --all-groups --frozen --python 3.12
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
