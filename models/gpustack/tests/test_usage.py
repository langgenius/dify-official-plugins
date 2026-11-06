import json
from unittest.mock import Mock

import pytest
import requests
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
)

from models.llm.llm import GPUStackLanguageModel


@pytest.mark.parametrize("mode", ["completion", "chat"])
@pytest.mark.parametrize("usage", [None, {"prompt_tokens": 0}, {"completion_tokens": 0}])
def test_usage_fills_only_missing_fields(monkeypatch, mode, usage):
    choice = {"text": "Answer"} if mode == "completion" else {"message": {"content": "Answer"}}
    response = requests.Response()
    response.status_code = 200
    response.encoding = "utf-8"
    response._content = json.dumps({"choices": [choice], "usage": usage}).encode()
    response._content_consumed = True
    monkeypatch.setattr(requests, "post", Mock(return_value=response))
    prompts = [
        UserPromptMessage(content=[TextPromptMessageContent(data="Hello world")]),
        AssistantPromptMessage(content="history"),
    ]

    chunks = list(
        GPUStackLanguageModel([]).invoke(
            "model",
            {"mode": mode, "endpoint_url": "https://example.test/v1", "api_key": "test-key"},
            prompts,
            stream=False,
        )
    )

    estimated = 2 if mode == "completion" else 15
    assert chunks[-1].delta.usage.prompt_tokens == (usage or {}).get("prompt_tokens", estimated)
    assert chunks[-1].delta.usage.completion_tokens == (usage or {}).get("completion_tokens", 1)
