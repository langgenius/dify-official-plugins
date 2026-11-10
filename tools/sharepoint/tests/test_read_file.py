"""sharepoint_read_file: the text of text, Word, Excel, PowerPoint and PDF files."""
import importlib
import io
import zipfile

import pytest

from test_sharepoint_tools import FILE, SITE, FakeResponse, run
from tools.text_extract import UnreadableFile, extract_text, kind_of

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
S = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
PKG = 'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"'


def office(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def pdf(text: str) -> bytes:
    """A one-page PDF showing ``text``, with a correct cross-reference table."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return out


DOCX = office({"word/document.xml": f'<w:document {W}><w:body><w:p><w:r><w:t>Quarterly</w:t></w:r><w:r><w:tab/>'
               '<w:t>report</w:t></w:r></w:p><w:p><w:r><w:t>Revenue up</w:t></w:r></w:p></w:body></w:document>'})
PPTX = office({
    "ppt/slides/slide10.xml": f"<p:sld {A}><a:p><a:r><a:t>Last</a:t></a:r></a:p></p:sld>".replace("<p:sld", '<p:sld xmlns:p="p"'),
    "ppt/slides/slide2.xml": f"<p:sld {A}><a:p><a:r><a:t>Second</a:t></a:r></a:p></p:sld>".replace("<p:sld", '<p:sld xmlns:p="p"'),
})
XLSX = office({
    "xl/workbook.xml": f'<workbook {S} {R}><sheets><sheet name="Scores" sheetId="1" r:id="rId1"/></sheets></workbook>',
    "xl/_rels/workbook.xml.rels": f'<Relationships {PKG}><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
    "xl/sharedStrings.xml": f"<sst {S}><si><t>Name</t></si><si><t>Kim</t></si></sst>",
    "xl/worksheets/sheet1.xml": f'<worksheet {S}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1" t="inlineStr">'
                                '<is><t>Score</t></is></c></row><row r="2"><c r="A2" t="s"><v>1</v></c><c r="C2"><v>90</v></c>'
                                '</row></sheetData></worksheet>',
})


@pytest.mark.parametrize(("name", "mime", "kind"), [
    ("notes.txt", "", "text"), ("data.CSV", "application/octet-stream", "text"), ("x", "application/json", "text"),
    ("a.docx", "", "docx"), ("a.xlsx", "", "xlsx"), ("a.pptx", "", "pptx"), ("a.pdf", "", "pdf"),
    ("photo.png", "image/png", None), ("old.doc", "application/msword", None),
])
def test_kind_of(name, mime, kind):
    assert kind_of(name, mime) == kind


def test_office_and_pdf_text():
    assert extract_text("docx", DOCX) == "Quarterly\treport\nRevenue up"
    assert extract_text("pptx", PPTX) == "## Slide 1\nSecond\n\n## Slide 2\nLast"
    assert extract_text("xlsx", XLSX) == "## Scores\nName\t\tScore\nKim\t\t90"
    assert "Hello PDF" in extract_text("pdf", pdf("Hello PDF"))
    assert extract_text("text", "héllo".encode("utf-16")) == "héllo"


def test_damaged_file_is_reported():
    with pytest.raises(UnreadableFile, match="damaged"):
        extract_text("docx", b"not a zip")


def read(monkeypatch, item, content, **params):
    seen = []
    monkeypatch.setattr(importlib.import_module("tools.sharepoint_read_file").requests, "get",
                        lambda url, timeout=None, **kw: seen.append((url, kw)) or FakeResponse(None, 200, content))
    _, out, texts, _ = run("sharepoint_read_file", {"file_id": "f1", **params},
                           {("GET", f"{SITE}/drive/items/f1"): FakeResponse(item)}, monkeypatch)
    return out, texts, seen


def test_reads_a_word_file_without_sending_the_token(monkeypatch):
    out, texts, seen = read(monkeypatch, dict(FILE, name="report.docx"), DOCX)
    assert seen == [("https://download.example/a", {})]
    assert out["content"] == "Quarterly\treport\nRevenue up" and out["success"] is True and out["truncated"] is False
    assert texts[0].startswith("# report.docx\n\nQuarterly")


def test_long_text_is_truncated(monkeypatch):
    out, texts, _ = read(monkeypatch, FILE, b"x" * 50, max_chars=10)
    assert out["content"] == "x" * 10 and out["length"] == 50 and out["truncated"] is True
    assert "showing 10 of 50 characters" in texts[0]


def test_unsupported_type_and_folder_are_refused_before_downloading(monkeypatch):
    out, _, seen = read(monkeypatch, dict(FILE, name="photo.png", file={"mimeType": "image/png"}), b"")
    assert out["success"] is False and "cannot be read as text" in out["error"] and seen == []
    out, _, seen = read(monkeypatch, {"id": "f1", "name": "Docs", "folder": {}}, b"")
    assert "is a folder" in out["error"] and seen == []
