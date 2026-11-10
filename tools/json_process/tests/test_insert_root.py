import json
import runpy
from pathlib import Path

import pytest
from dify_plugin.entities.tool import ToolRuntime


@pytest.mark.parametrize("original", [None, False, 0, "old"])
def test_insert_updates_scalar_root(original):
    cls = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tools/insert.py"))[
        "JSONParseTool"
    ]
    tool = cls(
        runtime=ToolRuntime(credentials={}, user_id="test", session_id="test"),
        session=None,
    )
    messages = list(
        tool.invoke(
            {
                "content": json.dumps(original),
                "query": "$",
                "new_value": '{"answer": 42}',
                "value_decode": True,
            }
        )
    )
    assert len(messages) == 1
    assert json.loads(messages[0].message.text) == {"answer": 42}
