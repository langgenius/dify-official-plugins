import json

import httpx
import pytest
from dify_plugin.entities.model.llm import LLMUsage
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    ToolPromptMessage,
    UserPromptMessage,
)
from models.llm import llm as module
from openai import OpenAI


@pytest.mark.parametrize("stream", [False, True])
def test_legacy_function_call_is_complete_and_replayed_by_name(monkeypatch, stream):
    payloads = []

    def respond(request):
        payloads.append(json.loads(request.content))
        if not stream:
            return httpx.Response(
                200,
                json={
                    "id": "response",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "model",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "function_call",
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "function_call": {
                                    "name": "weather",
                                    "arguments": '{"city":"Tokyo"}',
                                },
                            },
                        }
                    ],
                },
            )
        deltas = [
            ({"function_call": {"name": "weather", "arguments": '{"city":"'}}, None),
            ({"function_call": {"arguments": "Tokyo"}}, None),
            ({"function_call": {"arguments": '"}'}}, None),
            ({}, "function_call"),
        ]
        frames = [
            {
                "id": "response",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "model",
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            for delta, finish in deltas
        ]
        return httpx.Response(
            200,
            text="".join(f"data: {json.dumps(frame)}\n\n" for frame in frames)
            + "data: [DONE]\n\n",
        )

    client = OpenAI(
        api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(respond))
    )
    monkeypatch.setattr(module, "OpenAI", lambda **kwargs: client)
    llm = module.LocalAILanguageModel([])
    llm._num_tokens_from_messages = lambda *args, **kwargs: 1
    llm._calc_response_usage = lambda *args, **kwargs: LLMUsage.empty_usage()
    kwargs = {
        "model": "model",
        "credentials": {
            "completion_type": "chat_completion",
            "server_url": "https://example.test",
        },
        "model_parameters": {},
        "tools": [
            PromptMessageTool(
                name="weather", description="Weather", parameters={"type": "object"}
            )
        ],
        "stream": stream,
    }
    try:
        results = []
        prompts = [UserPromptMessage(content="Weather?")]
        for _ in range(2):
            result = llm._generate(prompt_messages=prompts, **kwargs)
            if stream:
                calls = [
                    call for chunk in result for call in chunk.delta.message.tool_calls
                ]
            else:
                calls = result.message.tool_calls
            assert len(calls) == 1
            call = calls[0]
            assert call.id and call.id != "0"
            assert call.function.name == "weather"
            assert json.loads(call.function.arguments) == {"city": "Tokyo"}
            results.append(call)
            prompts = [
                *prompts,
                AssistantPromptMessage(content="", tool_calls=calls),
                ToolPromptMessage(content="Sunny", tool_call_id=call.id),
            ]
        assert results[0].id != results[1].id
        assert payloads[0]["functions"][0]["name"] == "weather"
        assert payloads[1]["messages"][-1] == {
            "role": "function",
            "content": "Sunny",
            "name": "weather",
        }
    finally:
        client.close()
