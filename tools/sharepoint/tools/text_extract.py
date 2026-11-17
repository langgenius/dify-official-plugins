"""
The text of a document library file, so an agent can read it without a file output: plain text
formats, Word (.docx), Excel (.xlsx), PowerPoint (.pptx) and PDF.

Office files are zip archives of XML; their text is read with the standard library. Members are
read with a size cap, so a small archive cannot expand into gigabytes.
"""

import io
import posixpath
import re
import zipfile
from xml.etree import ElementTree

from pypdf import PdfReader
from pypdf.errors import PdfReadError

# Extensions read as text, whatever MIME type SharePoint reports for them.
TEXT_EXTENSIONS = {
    "txt", "md", "markdown", "csv", "tsv", "json", "xml", "html", "htm", "log", "yaml", "yml", "ini", "rtf", "sql",
}
_MAX_MEMBER = 50 * 1024 * 1024

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class UnreadableFile(Exception):
    """The file is not a format this tool can read, or it is damaged."""


def kind_of(name: str, mime_type: str) -> str | None:
    """Which reader handles the file: text, docx, xlsx, pptx, pdf, or None."""
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension in ("docx", "xlsx", "pptx", "pdf"):
        return extension
    if extension in TEXT_EXTENSIONS or mime_type.startswith("text/") or mime_type in ("application/json", "application/xml"):
        return "text"
    return None


def extract_text(kind: str, content: bytes) -> str:
    try:
        if kind == "text":
            return _decode(content)
        if kind == "pdf":
            return _pdf(content)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return {"docx": _docx, "xlsx": _xlsx, "pptx": _pptx}[kind](archive)
    except (zipfile.BadZipFile, ElementTree.ParseError, PdfReadError, KeyError) as e:
        raise UnreadableFile(f"the file could not be read ({e.__class__.__name__}); it may be damaged or protected") from e


def _decode(content: bytes) -> str:
    if content[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return content.decode("utf-16", "replace")
    return content.decode("utf-8-sig", "replace")


def _xml(archive: zipfile.ZipFile, name: str) -> ElementTree.Element:
    info = archive.getinfo(name)
    if info.file_size > _MAX_MEMBER:
        raise UnreadableFile(f"{name} inside the file is too large to read")
    return ElementTree.fromstring(archive.read(info))


def _paragraphs(root: ElementTree.Element, ns: str) -> list[str]:
    lines = []
    for paragraph in root.iter(f"{ns}p"):
        parts = []
        for node in paragraph.iter():
            if node.tag == f"{ns}t" and node.text:
                parts.append(node.text)
            elif node.tag in (f"{ns}tab",):
                parts.append("\t")
            elif node.tag in (f"{ns}br", f"{ns}cr"):
                parts.append("\n")
        lines.append("".join(parts))
    return lines


def _docx(archive: zipfile.ZipFile) -> str:
    return "\n".join(_paragraphs(_xml(archive, "word/document.xml"), _W)).strip()


def _pptx(archive: zipfile.ZipFile) -> str:
    slides = sorted(
        (n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
        key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)),
    )
    parts = []
    for number, name in enumerate(slides, 1):
        text = "\n".join(line for line in _paragraphs(_xml(archive, name), _A) if line.strip())
        parts.append(f"## Slide {number}\n{text}".rstrip())
    return "\n\n".join(parts)


def _xlsx(archive: zipfile.ZipFile) -> str:
    shared = []
    if "xl/sharedStrings.xml" in archive.namelist():
        for item in _xml(archive, "xl/sharedStrings.xml").iter(f"{_S}si"):
            shared.append("".join(t.text or "" for t in item.iter(f"{_S}t")))
    targets = {
        rel.get("Id"): posixpath.normpath(posixpath.join("xl", rel.get("Target", "").lstrip("/").removeprefix("xl/")))
        for rel in _xml(archive, "xl/_rels/workbook.xml.rels").iter(f"{_PKG}Relationship")
    }
    parts = []
    for sheet in _xml(archive, "xl/workbook.xml").iter(f"{_S}sheet"):
        path = targets.get(sheet.get(f"{_R}id"))
        if not path or path not in archive.namelist():
            continue
        rows = []
        for row in _xml(archive, path).iter(f"{_S}row"):
            cells = []
            for cell in row.iter(f"{_S}c"):
                column = _column(cell.get("r", ""))
                while column is not None and len(cells) < column:
                    cells.append("")
                cells.append(_cell(cell, shared))
            while cells and not cells[-1]:
                cells.pop()
            if cells:
                rows.append("\t".join(cells))
        parts.append(f"## {sheet.get('name', 'Sheet')}\n" + "\n".join(rows))
    return "\n\n".join(parts).strip()


def _column(reference: str) -> int | None:
    """Zero-based column of a cell reference like 'C7'."""
    letters = re.match(r"[A-Z]+", reference)
    if not letters:
        return None
    number = 0
    for letter in letters.group(0):
        number = number * 26 + ord(letter) - 64
    return number - 1


def _cell(cell: ElementTree.Element, shared: list[str]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{_S}t"))
    value = cell.find(f"{_S}v")
    text = value.text if value is not None and value.text is not None else ""
    if kind == "s" and text.isdigit() and int(text) < len(shared):
        return shared[int(text)]
    if kind == "b":
        return "TRUE" if text == "1" else "FALSE"
    return text


def _pdf(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted:
        raise UnreadableFile("the PDF is password-protected")
    pages = []
    for number, page in enumerate(reader.pages, 1):
        pages.append(f"## Page {number}\n{(page.extract_text() or '').strip()}".rstrip())
    return "\n\n".join(pages)
