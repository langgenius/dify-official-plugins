import json
import runpy
from pathlib import Path
from typing import Any

import pytest
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolRuntime


@pytest.fixture
def tool() -> Tool:
    source = Path(__file__).resolve().parents[1] / "tools" / "replace.py"
    tool_class = runpy.run_path(str(source))["JSONReplaceTool"]
    return tool_class(
        runtime=ToolRuntime(credentials={}, user_id="test", session_id="test"),
        session=None,
    )


def invoke(tool: Tool, **parameters: Any) -> str:
    messages = list(tool.invoke(parameters))
    assert len(messages) == 1
    return messages[0].message.text


@pytest.mark.parametrize(
    "original,replacement",
    [
        ({"before": 1}, {"after": 2}),
        ([1, 2], [3]),
        ("old", "new"),
        (7, 0),
        (True, False),
        (None, {"after": 2}),
    ],
)
def test_replace_root_value(tool: Tool, original: Any, replacement: Any) -> None:
    result = invoke(
        tool,
        content=json.dumps(original),
        query="$",
        replace_model="value",
        replace_value=json.dumps(replacement),
        value_decode=True,
    )
    assert json.loads(result) == replacement


@pytest.mark.parametrize(
    "replacement,value_decode,expected",
    [("new", False, "new"), ('{"after": 2}', True, {"after": 2})],
)
def test_replace_pattern_in_root_string(
    tool: Tool, replacement: str, value_decode: bool, expected: Any
) -> None:
    result = invoke(
        tool,
        content='"old"',
        query="$",
        replace_model="pattern",
        replace_pattern="old",
        replace_value=replacement,
        value_decode=value_decode,
    )
    assert json.loads(result) == expected


@pytest.mark.parametrize("ensure_ascii", [False, True])
def test_root_replacement_encoding(tool: Tool, ensure_ascii: bool) -> None:
    result = invoke(
        tool,
        content="null",
        query="$",
        replace_model="value",
        replace_value="你好",
        ensure_ascii=ensure_ascii,
    )
    assert json.loads(result) == "你好"
    assert ("你好" in result) is not ensure_ascii


@pytest.mark.parametrize("query", ["$.value", "$[0]"])
@pytest.mark.parametrize("mode", ["value", "pattern"])
def test_replace_nested_value(tool: Tool, query: str, mode: str) -> None:
    original = {"value": "old", "keep": "old"} if query == "$.value" else ["old", "keep"]
    expected = {"value": "new", "keep": "old"} if query == "$.value" else ["new", "keep"]
    result = invoke(
        tool,
        content=json.dumps(original),
        query=query,
        replace_model=mode,
        replace_value="new",
        replace_pattern="old",
    )
    assert json.loads(result) == expected


def test_replace_all_matching_values(tool: Tool) -> None:
    result = invoke(
        tool,
        content='{"values": ["old", "old"], "keep": "old"}',
        query="$.values[*]",
        replace_model="value",
        replace_value="new",
    )
    assert json.loads(result) == {"values": ["new", "new"], "keep": "old"}


def test_replace_key(tool: Tool) -> None:
    result = invoke(
        tool,
        content='{"old": 1, "keep": 2}',
        query="$.old",
        replace_model="key",
        replace_value="new",
    )
    assert json.loads(result) == {"new": 1, "keep": 2}


def test_replace_with_no_matches(tool: Tool) -> None:
    result = invoke(
        tool,
        content='{"keep": 1}',
        query="$.missing",
        replace_model="value",
        replace_value="new",
    )
    assert json.loads(result) == {"keep": 1}
