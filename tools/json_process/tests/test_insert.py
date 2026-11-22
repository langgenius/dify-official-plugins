import json
import runpy
from pathlib import Path

import pytest
from dify_plugin.entities.tool import ToolRuntime


@pytest.mark.parametrize(
    "create_path,expected",
    [
        ("False", {"keep": 1}),
        (False, {"keep": 1}),
        ("True", {"keep": 1, "new": "value"}),
        (True, {"keep": 1, "new": "value"}),
    ],
)
def test_insert_respects_create_path_selection(create_path, expected):
    source = Path(__file__).resolve().parents[1] / "tools" / "insert.py"
    tool_class = runpy.run_path(str(source))["JSONParseTool"]
    tool = tool_class(
        runtime=ToolRuntime(credentials={}, user_id="test", session_id="test"),
        session=None,
    )
    messages = list(
        tool.invoke(
            {
                "content": '{"keep": 1}',
                "query": "$.new",
                "new_value": "value",
                "create_path": create_path,
            }
        )
    )
    assert len(messages) == 1
    assert json.loads(messages[0].message.text) == expected


@pytest.mark.parametrize(
    "parameters,expected_message",
    [
        (
            {"content": "", "query": "$.a", "new_value": "x"},
            "Invalid parameter content",
        ),
        (
            {"content": '{"a": 1}', "query": "", "new_value": "x"},
            "Invalid parameter query",
        ),
        (
            {"content": '{"a": 1}', "query": "$.a", "new_value": ""},
            "Invalid parameter new_value",
        ),
    ],
)
def test_insert_stops_after_invalid_parameter(parameters, expected_message):
    """An invalid parameter must yield exactly one message.

    Regression test: _invoke() used to keep running after yielding an
    "Invalid parameter ..." message, so one invalid call returned two
    contradictory messages (the validation error plus the result or
    error of the operation that ran anyway).
    """
    source = Path(__file__).resolve().parents[1] / "tools" / "insert.py"
    tool_class = runpy.run_path(str(source))["JSONParseTool"]
    tool = tool_class(
        runtime=ToolRuntime(credentials={}, user_id="test", session_id="test"),
        session=None,
    )
    messages = list(tool.invoke(parameters))
    assert len(messages) == 1
    assert messages[0].message.text == expected_message
