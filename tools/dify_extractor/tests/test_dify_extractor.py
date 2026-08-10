from types import SimpleNamespace

import pytest

from tools.dify_extractor import DifyExtractorTool
from tools.document import Document, ExtractorResult
from tools.errors import ExtractionError
from tools.extractor_base import BaseExtractor


class _MessageToolMixin:
    def create_text_message(self, value):
        return {"type": "text", "value": value}

    def create_variable_message(self, name, value):
        return {"type": "variable", "name": name, "value": value}


def _make_tool() -> DifyExtractorTool:
    tool = object.__new__(DifyExtractorTool)
    tool.create_text_message = _MessageToolMixin.create_text_message.__get__(
        tool, DifyExtractorTool
    )
    tool.create_variable_message = _MessageToolMixin.create_variable_message.__get__(
        tool, DifyExtractorTool
    )
    return tool


def _file(
    blob: bytes,
    filename: str | None = "sample.txt",
    extension: str | None = None,
    mime_type: str | None = "text/plain",
):
    return SimpleNamespace(
        filename=filename,
        extension=extension,
        mime_type=mime_type,
        blob=blob,
    )


def test_success_preserves_message_order_and_outputs():
    messages = list(_make_tool()._invoke({"file": _file(b"hello")}))

    assert [message["type"] for message in messages] == ["text", "variable"]
    assert messages[0]["value"] == "hello"
    assert messages[1]["name"] == "documents"
    assert messages[1]["value"][0].metadata == {"source": "sample.txt"}


def test_missing_file_returns_one_error_message():
    messages = list(_make_tool()._invoke({}))

    assert messages == [{"type": "text", "value": "A file is required."}]


def test_missing_filename_uses_supplied_extension():
    messages = list(
        _make_tool()._invoke(
            {"file": _file(b"hello", filename=None, extension="txt", mime_type=None)}
        )
    )

    assert messages[0]["value"] == "hello"
    assert messages[1]["value"][0].metadata["source"] == "uploaded.txt"


def test_supplied_extension_resolves_misnamed_file():
    messages = list(
        _make_tool()._invoke(
            {
                "file": _file(
                    b'{"answer": 42}',
                    filename="payload.bin",
                    extension="json",
                    mime_type="application/json",
                )
            }
        )
    )

    assert messages[0]["value"].startswith("```json")


def test_text_mime_type_enables_smart_fallback():
    messages = list(
        _make_tool()._invoke(
            {"file": _file(b"plain", filename="sample.unknown", mime_type="text/plain")}
        )
    )

    assert messages[0]["value"] == "plain"


def test_unsupported_binary_returns_one_error_message():
    messages = list(
        _make_tool()._invoke(
            {
                "file": _file(
                    b"binary",
                    filename="archive.zip",
                    mime_type="application/zip",
                )
            }
        )
    )

    assert len(messages) == 1
    assert "Unsupported file format '.zip'" in messages[0]["value"]


def test_empty_file_returns_one_error_message():
    messages = list(_make_tool()._invoke({"file": _file(b"")}))

    assert messages == [{"type": "text", "value": "File 'sample.txt' is empty."}]


def test_blob_read_failure_is_actionable():
    class BrokenFile:
        filename = "report.txt"
        extension = ".txt"
        mime_type = "text/plain"

        @property
        def blob(self):
            raise ConnectionError("secret internal URL")

    messages = list(_make_tool()._invoke({"file": BrokenFile()}))

    assert len(messages) == 1
    assert "FILES_URL" in messages[0]["value"]
    assert "secret internal URL" not in messages[0]["value"]


def test_invalid_json_returns_error_without_document_variables():
    messages = list(
        _make_tool()._invoke(
            {
                "file": _file(
                    b"{broken",
                    filename="payload.json",
                    mime_type="application/json",
                )
            }
        )
    )

    assert len(messages) == 1
    assert "invalid JSON" in messages[0]["value"]


def test_header_only_csv_is_rejected_as_empty_content():
    messages = list(
        _make_tool()._invoke(
            {"file": _file(b"name,age\n", filename="people.csv", mime_type="text/csv")}
        )
    )

    assert len(messages) == 1
    assert "contains no extractable content" in messages[0]["value"]


@pytest.mark.parametrize(
    ("extension", "format_hint"),
    [
        (".docx", "old binary .doc instead of .docx"),
        (".pptx", "old binary .ppt instead of .pptx"),
        (".xlsx", "old binary .xls instead of .xlsx"),
    ],
)
def test_corrupt_office_file_returns_tailored_error(extension, format_hint):
    filename = f"report{extension}"
    messages = list(
        _make_tool()._invoke({"file": _file(b"not a zip file", filename=filename, mime_type=None)})
    )

    assert len(messages) == 1
    assert f"not a valid {extension} file" in messages[0]["value"]
    assert format_hint in messages[0]["value"]


def test_unexpected_extractor_error_is_sanitized(monkeypatch):
    class BrokenExtractor(BaseExtractor):
        def extract(self):
            raise RuntimeError("database password")

    monkeypatch.setitem(
        __import__("tools.dify_extractor", fromlist=["_EXTRACTORS"])._EXTRACTORS,
        ".txt",
        BrokenExtractor,
    )
    messages = list(_make_tool()._invoke({"file": _file(b"hello")}))

    assert len(messages) == 1
    assert "database password" not in messages[0]["value"]
    assert "plugin logs" in messages[0]["value"]


def test_result_validation_accepts_only_meaningful_documents():
    with pytest.raises(ExtractionError, match="no extractable content"):
        DifyExtractorTool._validate_result(
            ExtractorResult(md_content="heading", documents=[Document(page_content="")]),
            "empty.txt",
        )
