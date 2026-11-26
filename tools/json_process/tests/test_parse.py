import runpy
from pathlib import Path

import pytest
from dify_plugin.entities.tool import ToolRuntime


def _load_tool():
    source = Path(__file__).resolve().parents[1] / "tools" / "parse.py"
    tool_class = runpy.run_path(str(source))["JSONParseTool"]
    return tool_class(
        runtime=ToolRuntime(credentials={}, user_id="test", session_id="test"),
        session=None,
    )


def test_parse_extracts_matching_value():
    tool = _load_tool()
    messages = list(
        tool.invoke({"content": '{"a": 1}', "json_filter": "$.a"})
    )
    assert len(messages) == 1
    assert messages[0].message.text == "1"


@pytest.mark.parametrize(
    "parameters,expected_message",
    [
        (
            {"content": "", "json_filter": "$.a"},
            "Invalid parameter content",
        ),
        (
            {"content": '{"a": 1}', "json_filter": ""},
            "Invalid parameter json_filter",
        ),
    ],
)
def test_parse_stops_after_invalid_parameter(parameters, expected_message):
    """An invalid parameter must yield exactly one message.

    Regression test: _invoke() used to keep running after yielding an
    "Invalid parameter ..." message, so one invalid call returned two
    contradictory messages (the validation error plus the result or
    error of the operation that ran anyway).
    """
    tool = _load_tool()
    messages = list(tool.invoke(parameters))
    assert len(messages) == 1
    assert messages[0].message.text == expected_message
