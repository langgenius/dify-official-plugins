import runpy
from pathlib import Path

import pytest
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolRuntime


@pytest.fixture
def tool() -> Tool:
    source = Path(__file__).resolve().parents[1] / "tools" / "regex_extract.py"
    tool_class = runpy.run_path(str(source))["RegexExpressionTool"]
    return tool_class(
        runtime=ToolRuntime(credentials={}, user_id="test", session_id="test"),
        session=None,
    )


@pytest.mark.parametrize(
    "content,expression,expected",
    [
        ("a b  c", " ", [" ", " ", " "]),
        ("a foo b", " foo ", [" foo "]),
        (" foo ", r"^\s+foo\s+$", [" foo "]),
        ("foo\n", r"\n$", ["\n"]),
        ("\tfoo\t", r"^\tfoo\t$", ["\tfoo\t"]),
        (" ", r"\s", [" "]),
        ("id=42", r"\d+", ["42"]),
        ("abc", r"\d+", []),
        ("a=1 b=2", r"([a-z])=(\d)", [("a", "1"), ("b", "2")]),
    ],
)
def test_extract(tool: Tool, content: str, expression: str, expected: list) -> None:
    messages = list(tool.invoke({"content": content, "expression": expression}))
    assert len(messages) == 1
    assert messages[0].message.text == str(expected)


def test_invalid_pattern(tool: Tool) -> None:
    messages = list(tool.invoke({"content": "abc", "expression": "["}))
    assert len(messages) == 1
    assert messages[0].message.text.startswith("Failed to extract result, error:")
