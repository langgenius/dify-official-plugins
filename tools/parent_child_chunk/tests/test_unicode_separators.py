from unittest.mock import Mock

import pytest
from dify_plugin.core.runtime import Session
from dify_plugin.entities.tool import ToolRuntime

from tools.parent_child_chunk import ParentChildChunkTool


@pytest.fixture(
    params=[
        pytest.param(("。", "。"), id="chinese-period"),
        pytest.param(("😀", "😀"), id="emoji"),
        pytest.param(("|", "|"), id="ascii"),
        pytest.param((r"\n", "\n"), id="escaped-newline"),
        pytest.param((r"\u3002", "。"), id="escaped-codepoint"),
        pytest.param((r"。\n", "。\n"), id="unicode-and-escape"),
    ]
)
def separator_case(request):
    return request.param


def invoke_chunker(text, parent_mode, parent_separator, child_separator):
    tool = ParentChildChunkTool(
        runtime=ToolRuntime(credentials={}, user_id=None, session_id=None),
        session=Mock(spec=Session),
    )
    (result,) = tool.invoke(
        {
            "input_text": text,
            "parent_mode": parent_mode,
            "separator": parent_separator,
            "subchunk_separator": child_separator,
            "max_length": 256,
            "subchunk_max_length": 256,
        }
    )
    return result.message.variable_value.parent_child_chunks


def test_parent_separator(separator_case):
    configured, literal = separator_case
    text = f"第一段 Alpha{literal}Beta 第二段"

    chunks = invoke_chunker(
        text, "paragraph", parent_separator=configured, child_separator="~"
    )

    assert [chunk.parent_content for chunk in chunks] == ["第一段 Alpha", "Beta 第二段"]
    assert [chunk.child_contents for chunk in chunks] == [
        ["第一段 Alpha"],
        ["Beta 第二段"],
    ]


@pytest.mark.parametrize("parent_mode", ["paragraph", "full_doc"])
def test_child_separator(separator_case, parent_mode):
    configured, literal = separator_case
    text = f"第一段 Alpha{literal}Beta 第二段"

    (parent,) = invoke_chunker(
        text, parent_mode, parent_separator="~", child_separator=configured
    )

    assert parent.parent_content == text
    assert parent.child_contents == ["第一段 Alpha", "Beta 第二段"]
