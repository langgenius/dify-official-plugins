import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.dify_extractor import DifyExtractorTool


class _MessageToolMixin:
    def create_text_message(self, value):
        return {"type": "text", "value": value}

    def create_variable_message(self, name, value):
        return {"type": "variable", "name": name, "value": value}


def _make_tool() -> DifyExtractorTool:
    tool = object.__new__(DifyExtractorTool)
    tool.create_text_message = _MessageToolMixin.create_text_message.__get__(tool, DifyExtractorTool)
    tool.create_variable_message = _MessageToolMixin.create_variable_message.__get__(tool, DifyExtractorTool)
    return tool


def test_invoke_returns_error_for_corrupt_docx():
    tool = _make_tool()
    corrupt_file = SimpleNamespace(filename="report.docx", blob=b"not a zip file")

    messages = list(tool._invoke({"file": corrupt_file}))

    assert len(messages) == 1
    assert messages[0]["type"] == "text"
    assert "not a valid .docx file" in messages[0]["value"]
    assert "old binary .doc instead of .docx" in messages[0]["value"]


def test_invoke_returns_error_for_corrupt_pptx():
    tool = _make_tool()
    corrupt_file = SimpleNamespace(filename="slides.pptx", blob=b"not a zip file")

    messages = list(tool._invoke({"file": corrupt_file}))

    assert len(messages) == 1
    assert messages[0]["type"] == "text"
    assert "not a valid .pptx file" in messages[0]["value"]
    assert "old binary .ppt instead of .pptx" in messages[0]["value"]


def test_invoke_returns_error_for_corrupt_xlsx():
    tool = _make_tool()
    corrupt_file = SimpleNamespace(filename="sheet.xlsx", blob=b"not a zip file")

    messages = list(tool._invoke({"file": corrupt_file}))

    assert len(messages) == 1
    assert messages[0]["type"] == "text"
    assert "not a valid .xlsx file" in messages[0]["value"]
    assert "old binary .xls instead of .xlsx" in messages[0]["value"]
