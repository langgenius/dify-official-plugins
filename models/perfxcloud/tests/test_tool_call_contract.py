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
from dify_plugin.errors.model import InvokeError
from models.llm import openai_llm as module
from models.llm.llm import PerfXCloudLargeLanguageModel
from openai import OpenAI


@pytest.fixture
def provider(monkeypatch):
    llm = PerfXCloudLargeLanguageModel([])
    monkeypatch.setattr(llm, "_to_credential_kwargs", lambda credentials: {})
    monkeypatch.setattr(llm, "_num_tokens_from_messages", lambda *args: 1)

    def calculate_usage(model, credentials, prompt_tokens, completion_tokens):
        return LLMUsage.empty_usage().model_copy(
            update={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            }
        )

    monkeypatch.setattr(llm, "_calc_response_usage", calculate_usage)
    requests, responses = [], []

    def respond(request):
        requests.append(json.loads(request.content))
        return responses.pop(0)

    with OpenAI(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(respond))) as client:
        monkeypatch.setattr(module, "OpenAI", lambda **kwargs: client)
        yield llm, requests, responses


def response(stream, arguments='{"city":"Tokyo"}', finish="function_call", usage=True):
    common = {"id": "response", "created": 0, "model": "model"}
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if not stream:
        return httpx.Response(
            200,
            json={
                **common,
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": finish,
                        "message": {
                            "role": "assistant",
                            "content": "Checking done",
                            "function_call": {"name": "weather", "arguments": arguments},
                        },
                    }
                ],
                "usage": totals if usage else None,
            },
        )

    deltas = [
        ({"content": "Checking ", "function_call": {"name": "wea", "arguments": arguments[:5]}}, None),
        ({"function_call": {"name": "ther", "arguments": arguments[5:-1]}}, None),
        ({"content": "done", "function_call": {"arguments": arguments[-1:]}}, finish),
    ]
    frames = [
        {
            **common,
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": delta, "finish_reason": reason}],
        }
        for delta, reason in deltas
    ]
    if usage:
        frames[0]["usage"] = {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
        frames.append({**common, "object": "chat.completion.chunk", "choices": [], "usage": totals})
    body = "".join(f"data: {json.dumps(frame)}\n\n" for frame in frames) + "data: [DONE]\n\n"
    return httpx.Response(200, text=body)


def invoke(llm, stream, messages=None):
    return llm._chat_generate(
        model="model",
        credentials={},
        model_parameters={},
        prompt_messages=messages or [UserPromptMessage(content="Weather?")],
        tools=[PromptMessageTool(name="weather", description="Weather", parameters={"type": "object"})],
        stream=stream,
    )


@pytest.mark.parametrize("stream", [False, True])
def test_complete_function_calls_replay_by_name(provider, monkeypatch, stream):
    llm, requests, responses = provider
    monkeypatch.setattr(llm, "_num_tokens_from_messages", lambda *args: pytest.fail("Reported usage must be used"))
    messages = [UserPromptMessage(content="Weather?")]
    seen_ids = set()
    for _ in range(2):
        responses.append(response(stream))
        result = invoke(llm, stream, messages)
        if stream:
            chunks = list(result)
            assert "".join(chunk.delta.message.content for chunk in chunks) == "Checking done"
            assert all(not chunk.delta.message.tool_calls for chunk in chunks[:-1])
            calls = [call for chunk in chunks for call in chunk.delta.message.tool_calls]
            usage = chunks[-1].delta.usage
        else:
            calls, usage = result.message.tool_calls, result.usage
        assert len(calls) == 1
        call = calls[0]
        assert call.id and call.id != "weather" and call.id not in seen_ids
        seen_ids.add(call.id)
        assert call.function.name == "weather"
        assert json.loads(call.function.arguments) == {"city": "Tokyo"}
        assert (usage.prompt_tokens, usage.completion_tokens) == (0, 0)
        messages += [
            AssistantPromptMessage(content="", tool_calls=calls),
            ToolPromptMessage(content="Sunny", tool_call_id=call.id),
        ]
    assert requests[0]["functions"][0]["name"] == "weather"
    assert requests[1]["messages"][-1] == {"role": "function", "content": "Sunny", "name": "weather"}


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("arguments", ['{"city":', "[]"])
def test_rejects_incomplete_function_arguments(provider, stream, arguments):
    llm, _, responses = provider
    responses.append(response(stream, arguments=arguments))
    with pytest.raises(InvokeError):
        result = invoke(llm, stream)
        if stream:
            list(result)


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("finish", ["length", "content_filter"])
def test_rejects_truncated_function_calls(provider, stream, finish):
    llm, _, responses = provider
    responses.append(response(stream, finish=finish))
    with pytest.raises(InvokeError):
        result = invoke(llm, stream)
        if stream:
            list(result)


def test_estimates_usage_from_complete_function_call(provider, monkeypatch):
    llm, _, responses = provider
    counted = []

    def count_tokens(model, messages, tools=None):
        counted.append(messages)
        return 7 if tools else 3

    monkeypatch.setattr(llm, "_num_tokens_from_messages", count_tokens)
    responses.append(response(True, usage=False))
    chunks = list(invoke(llm, True))
    assert (chunks[-1].delta.usage.prompt_tokens, chunks[-1].delta.usage.completion_tokens) == (7, 3)
    assert counted[1][0].content == "Checking done"
    assert counted[1][0].tool_calls == chunks[-1].delta.message.tool_calls
