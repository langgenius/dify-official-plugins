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
from models.llm import llm as module
from openai import OpenAI


@pytest.fixture
def provider(monkeypatch):
    llm = module.LlamaApiLargeLanguageModel([])
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


def response(stream, arguments='{"city":"Tokyo"}', finish="tool_calls", usage=True, duplicate_id=False):
    common = {"id": "response", "created": 0, "model": "model"}
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    calls = [
        {"id": "call_tokyo", "type": "function", "function": {"name": "weather", "arguments": arguments}},
        {"id": "call_paris", "type": "function", "function": {"name": "weather", "arguments": '{"city":"Paris"}'}},
        {"type": "function", "function": {"name": "weather", "arguments": '{"city":"London"}'}},
    ]
    if duplicate_id:
        calls[1]["id"] = calls[0]["id"]
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
                        "message": {"role": "assistant", "content": "Checking done", "tool_calls": calls},
                    }
                ],
                "usage": totals if usage else None,
            },
        )

    deltas = [
        (
            {
                "content": "Checking ",
                "tool_calls": [
                    {
                        "index": 1,
                        "id": calls[1]["id"],
                        "type": "function",
                        "function": {"name": "wea", "arguments": '{"city":'},
                    }
                ],
            },
            None,
        ),
        ({"tool_calls": [{"index": 0, **calls[0]}]}, None),
        (
            {
                "content": "done",
                "tool_calls": [
                    {"index": 2, **calls[2]},
                    {"index": 1, "function": {"name": "ther", "arguments": '"Paris"}'}},
                ],
            },
            finish,
        ),
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
def test_parallel_calls_are_complete_unique_and_replayable(provider, monkeypatch, stream):
    llm, requests, responses = provider
    monkeypatch.setattr(llm, "_num_tokens_from_messages", lambda *args: pytest.fail("Reported usage must be used"))
    responses.extend([response(stream), response(stream)])
    result = invoke(llm, stream)
    if stream:
        chunks = list(result)
        assert "".join(chunk.delta.message.content for chunk in chunks) == "Checking done"
        assert all(not chunk.delta.message.tool_calls for chunk in chunks[:-1])
        calls = [call for chunk in chunks for call in chunk.delta.message.tool_calls]
        usage = chunks[-1].delta.usage
    else:
        calls, usage = result.message.tool_calls, result.usage
    assert len(calls) == 3
    assert [call.id for call in calls[:2]] == ["call_tokyo", "call_paris"]
    assert len({call.id for call in calls}) == 3 and all(call.id for call in calls)
    assert [call.function.name for call in calls] == ["weather"] * 3
    assert [json.loads(call.function.arguments)["city"] for call in calls] == ["Tokyo", "Paris", "London"]
    assert (usage.prompt_tokens, usage.completion_tokens) == (0, 0)
    messages = [
        UserPromptMessage(content="Weather?"),
        AssistantPromptMessage(content="", tool_calls=calls),
        *[ToolPromptMessage(content="Sunny", tool_call_id=call.id) for call in calls],
    ]
    result = invoke(llm, stream, messages)
    if stream:
        list(result)
    assert requests[0]["tools"][0]["function"]["name"] == "weather"
    assert [item["tool_call_id"] for item in requests[1]["messages"][-3:]] == [call.id for call in calls]
    assert requests[1]["messages"][1]["tool_calls"] == [call.model_dump() for call in calls]


@pytest.mark.parametrize("stream", [False, True])
def test_rejects_duplicate_provider_call_ids(provider, stream):
    llm, _, responses = provider
    responses.append(response(stream, duplicate_id=True))
    with pytest.raises(InvokeError, match="duplicate tool call IDs"):
        result = invoke(llm, stream)
        if stream:
            for chunk in result:
                assert not chunk.delta.message.tool_calls


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("arguments", ['{"city":', "[]"])
def test_rejects_incomplete_tool_arguments(provider, stream, arguments):
    llm, _, responses = provider
    responses.append(response(stream, arguments=arguments))
    with pytest.raises(InvokeError):
        result = invoke(llm, stream)
        if stream:
            list(result)


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("finish", ["length", "content_filter"])
def test_rejects_truncated_tool_calls(provider, stream, finish):
    llm, _, responses = provider
    responses.append(response(stream, finish=finish))
    with pytest.raises(InvokeError):
        result = invoke(llm, stream)
        if stream:
            list(result)


def test_estimates_usage_from_all_complete_calls(provider, monkeypatch):
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
    assert len(counted[1][0].tool_calls) == 3
    assert counted[1][0].tool_calls == chunks[-1].delta.message.tool_calls
