import json
import runpy
from pathlib import Path

import pytest
from dify_plugin.entities.tool import ToolRuntime


@pytest.mark.parametrize("value", ["text", 0, False, None, {"key": 1}, [1, 2]])
def test_create_terminal_array_path_stores_value(value):
    tool_class = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "tools/insert.py")
    )["JSONParseTool"]
    tool = tool_class(
        runtime=ToolRuntime(credentials={}, user_id="test", session_id="test"),
        session=None,
    )
    messages = list(
        tool.invoke(
            {
                "content": '{"keep": 1}',
                "query": "$.items[2]",
                "new_value": json.dumps(value),
                "value_decode": True,
                "create_path": "True",
            }
        )
    )
    assert len(messages) == 1
    assert json.loads(messages[0].message.text) == {"keep": 1, "items": [{}, {}, value]}
