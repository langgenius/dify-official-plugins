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
