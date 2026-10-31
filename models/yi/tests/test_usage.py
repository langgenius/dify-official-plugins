import json
from unittest.mock import Mock

import pytest
import requests
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
)

from models.llm.llm import YiLargeLanguageModel


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("answer", ["Answer", "<|endoftext|>"])
def test_missing_usage_counts_text_with_the_sdk_hook(monkeypatch, stream, answer):
    choice = {
        "delta" if stream else "message": {"content": answer},
        "finish_reason": "stop",
    }
    payload = json.dumps({"choices": [choice]})
    response = requests.Response()
    response.status_code = 200
    response.encoding = "utf-8"
    response._content = (f"data: {payload}\n\ndata: [DONE]\n\n" if stream else payload).encode()
    response._content_consumed = True
    post = Mock(return_value=response)
    monkeypatch.setattr(requests, "post", post)
    prompts = [
        UserPromptMessage(content=[TextPromptMessageContent(data="Hello world")]),
        AssistantPromptMessage(content="history"),
    ]

    chunks = list(
        YiLargeLanguageModel([]).invoke(
            "yi-large",
            {"api_key": "test-key", "endpoint_url": "https://example.test/v1"},
            prompts,
            stream=stream,
        )
    )

    assert "".join(chunk.delta.message.get_text_content() for chunk in chunks) == answer
    usage = chunks[-1].delta.usage
    assert usage.prompt_tokens == 15
    assert usage.completion_tokens > 0
    if answer == "Answer":
        assert usage.completion_tokens == 1
    assert len(json.loads(post.call_args.kwargs["data"])["messages"]) == 2
