import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from werkzeug import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dify_plugin.entities.model.llm import (
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
    LLMUsage,
)
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    TextPromptMessageContent,
)
from endpoints.llm import OaicompatDifyModelEndpoint


@pytest.mark.parametrize("stream", [False, True])
def test_chat_completion_serializes_text_from_content_blocks(stream):
    message = AssistantPromptMessage(
        content=[
            TextPromptMessageContent(
                data="hello ", opaque_body={"signature": "private"}
            ),
            TextPromptMessageContent(data="world"),
        ],
        opaque_body={"reasoning": "encrypted"},
    )
    session = Mock()
    session.model.llm.invoke.return_value = (
        iter(
            [
                LLMResultChunk(
                    model="test", delta=LLMResultChunkDelta(index=0, message=message)
                )
            ]
        )
        if stream
        else LLMResult(model="test", message=message, usage=LLMUsage.empty_usage())
    )
    request = Request.from_values(
        method="POST",
        content_type="application/json",
        headers={"Authorization": "Bearer test"},
        data=json.dumps(
            {"messages": [{"role": "user", "content": "hello"}], "stream": stream}
        ),
    )
    response = OaicompatDifyModelEndpoint(session).invoke(
        request,
        {},
        {
            "api_key": "test",
            "llm": {"provider": "test", "model": "test", "mode": "chat"},
        },
    )
    body = response.get_data(as_text=True)
    choice = json.loads(body)["choices"][0]
    assert choice["delta" if stream else "message"]["content"] == "hello world"
    assert "private" not in body
    assert "encrypted" not in body
