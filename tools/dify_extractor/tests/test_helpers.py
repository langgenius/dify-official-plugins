from types import SimpleNamespace
from zipfile import BadZipFile

import pytest

from tools import helpers
from tools.errors import ExtractionError


class _FakeArchive:
    def __init__(self, entries):
        self._entries = entries

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def infolist(self):
        return self._entries


def _entry(file_size=1, compress_size=1):
    return SimpleNamespace(file_size=file_size, compress_size=compress_size)


def test_decode_text_handles_utf16_bom():
    assert helpers.decode_text("你好".encode("utf-16"), "hello.txt") == "你好"


def test_decode_text_fails_when_no_candidate_decodes(monkeypatch):
    monkeypatch.setattr(helpers.chardet, "detect_all", lambda _data: [{"encoding": "utf-8"}])

    with pytest.raises(ExtractionError, match="could not be decoded"):
        helpers.decode_text(b"\xff", "bad.txt", preferred_encoding="ascii")


def test_markdown_table_escapes_pipes_backslashes_and_newlines():
    rendered = helpers.render_markdown_table(["a|b"], [["x\\y\nnext"]])

    assert "a\\|b" in rendered
    assert "x\\\\y<br>next" in rendered


def test_archive_validation_maps_bad_zip_to_format_error(monkeypatch):
    def fail(_file):
        raise BadZipFile

    monkeypatch.setattr(helpers, "ZipFile", fail)

    with pytest.raises(ExtractionError, match="old binary .doc"):
        helpers.validate_office_archive(b"bad", "report.docx", ".docx")


def test_archive_entry_limit(monkeypatch):
    monkeypatch.setattr(helpers, "MAX_ARCHIVE_ENTRIES", 1)
    monkeypatch.setattr(helpers, "ZipFile", lambda _file: _FakeArchive([_entry(), _entry()]))

    with pytest.raises(ExtractionError, match="too many archive entries"):
        helpers.validate_office_archive(b"zip", "report.docx", ".docx")


def test_archive_expanded_size_limit(monkeypatch):
    monkeypatch.setattr(helpers, "MAX_ARCHIVE_UNCOMPRESSED_BYTES", 10)
    monkeypatch.setattr(helpers, "ZipFile", lambda _file: _FakeArchive([_entry(11, 5)]))

    with pytest.raises(ExtractionError, match="200 MiB safety limit"):
        helpers.validate_office_archive(b"zip", "report.xlsx", ".xlsx")


def test_archive_compression_ratio_limit(monkeypatch):
    monkeypatch.setattr(helpers, "MAX_ARCHIVE_COMPRESSION_RATIO", 2)
    monkeypatch.setattr(helpers, "ZipFile", lambda _file: _FakeArchive([_entry(10, 1)]))

    with pytest.raises(ExtractionError, match="compression-ratio"):
        helpers.validate_office_archive(b"zip", "report.pptx", ".pptx")
