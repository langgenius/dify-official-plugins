"""Exercise JSON Delete through the real SDK without a daemon or model calls."""

import json
import runpy
from pathlib import Path

import pytest
from dify_plugin.entities.tool import ToolRuntime

JSONDeleteTool = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tools/delete.py"))[
    "JSONDeleteTool"
]


@pytest.fixture
def tool():
    runtime = ToolRuntime(credentials={}, user_id="test-user", session_id="test-session")
    # This local tool only creates messages; it does not use a daemon session.
    return JSONDeleteTool(runtime=runtime, session=None)


@pytest.mark.parametrize(
    "content, query, expected",
    [
        ({"items": [1, 2, 1]}, "$.items[2]", {"items": [1, 2]}),
        ({"items": [1, 2, 1]}, "$.items[-1]", {"items": [1, 2]}),
        ({"items": [True, "middle", 1]}, "$.items[2]", {"items": [True, "middle"]}),
        (
            {"items": [{"id": 1}, {"id": 2}, {"id": 1}]},
            "$.items[2]",
            {"items": [{"id": 1}, {"id": 2}]},
        ),
        ({"items": [0, 1, 2]}, "$.items[1,1]", {"items": [0, 2]}),
        ({"items": [0, 1, 2]}, "$.items[1,-2]", {"items": [0, 2]}),
        ({"items": [0, 1, 2, 3, 4]}, "$.items[3,1]", {"items": [0, 2, 4]}),
        ({"items": [1, 2, 1, 3, 4]}, "$.items[2:4]", {"items": [1, 2, 4]}),
        ({"items": [0, 1, 2, 3, 4]}, "$.items[::-2]", {"items": [1, 3]}),
        (
            {"rows": [[1, 2, 1], [3, 4, 3]]},
            "$.rows[*][2]",
            {"rows": [[1, 2], [3, 4]]},
        ),
        ([1, 2, 1], "$[2]", [1, 2]),
        ({"items": [1, 2, 1]}, "$.items[*]", {"items": []}),
        ({"a": 1, "b": 2}, "$.a", {"b": 2}),
        ({"items": [1, 2]}, "$.missing", {"items": [1, 2]}),
    ],
)
def test_delete_preserves_unselected_values(tool, content, query, expected):
    messages = list(tool.invoke({"content": json.dumps(content), "query": query}))

    assert len(messages) == 1
    # Comparing JSON text also distinguishes Python's equal values True and 1.
    assert json.dumps(json.loads(messages[0].message.text)) == json.dumps(expected)


@pytest.mark.parametrize("ensure_ascii", [False, True])
def test_delete_retains_encoding_option(tool, ensure_ascii):
    messages = list(
        tool.invoke(
            {
                "content": '{"items": ["保留", "删除", "保留"]}',
                "query": "$.items[2]",
                "ensure_ascii": ensure_ascii,
            }
        )
    )

    assert messages[0].message.text == json.dumps(
        {"items": ["保留", "删除"]}, ensure_ascii=ensure_ascii
    )


def test_delete_reports_invalid_json(tool):
    messages = list(tool.invoke({"content": "not json", "query": "$.items[2]"}))

    assert len(messages) == 1
    assert messages[0].message.text.startswith("Failed to delete JSON content:")
