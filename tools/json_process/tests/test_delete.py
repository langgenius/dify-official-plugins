import json
import runpy
from pathlib import Path
from typing import Any

import pytest
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolRuntime


@pytest.fixture
def tool() -> Tool:
    source = Path(__file__).resolve().parents[1] / "tools" / "delete.py"
    tool_class = runpy.run_path(str(source))["JSONDeleteTool"]
    return tool_class(
        runtime=ToolRuntime(credentials={}, user_id="test", session_id="test"),
        session=None,
    )


def invoke(tool: Tool, **parameters: Any) -> str:
    messages = list(tool.invoke(parameters))
    assert len(messages) == 1
    return messages[0].message.text


def test_delete_dict_key(tool: Tool) -> None:
    result = invoke(
        tool,
        content='{"a": 1, "b": {"c": 2}}',
        query="$.b.c",
        ensure_ascii=True,
    )
    assert json.loads(result) == {"a": 1, "b": {}}


def test_delete_array_element_by_index(tool: Tool) -> None:
    result = invoke(
        tool,
        content='{"items": [1, 2, 3]}',
        query="$.items[1]",
        ensure_ascii=True,
    )
    assert json.loads(result) == {"items": [1, 3]}


def test_delete_array_element_with_duplicate_values(tool: Tool) -> None:
    result = invoke(
        tool,
        content='{"items": [1, 2, 1]}',
        query="$.items[2]",
        ensure_ascii=True,
    )
    # The trailing 1 is selected by index, not by value equality.
    assert json.loads(result) == {"items": [1, 2]}


def test_delete_array_element_negative_index(tool: Tool) -> None:
    result = invoke(
        tool,
        content='{"items": [1, 2, 3]}',
        query="$.items[-1]",
        ensure_ascii=True,
    )
    assert json.loads(result) == {"items": [1, 2]}


def test_delete_array_wildcard(tool: Tool) -> None:
    result = invoke(
        tool,
        content='{"items": [1, 2, 1]}',
        query="$.items[*]",
        ensure_ascii=True,
    )
    assert json.loads(result) == {"items": []}


def test_delete_array_slice(tool: Tool) -> None:
    result = invoke(
        tool,
        content='{"items": [1, 2, 3, 4]}',
        query="$.items[1:3]",
        ensure_ascii=True,
    )
    assert json.loads(result) == {"items": [1, 4]}


def test_delete_array_duplicate_objects(tool: Tool) -> None:
    result = invoke(
        tool,
        content='{"items": [{"x": 1}, {"x": 1}]}',
        query="$.items[1]",
        ensure_ascii=True,
    )
    assert json.loads(result) == {"items": [{"x": 1}]}


def test_delete_with_no_matches(tool: Tool) -> None:
    result = invoke(
        tool,
        content='{"items": [1, 2, 1]}',
        query="$.missing",
        ensure_ascii=True,
    )
    assert json.loads(result) == {"items": [1, 2, 1]}
