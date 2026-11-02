import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from azure.ai.inference.models import (
    ChatCompletions,
    StreamingChatCompletions,
    StreamingChatCompletionsUpdate,
)
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMUsage
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeError
from dify_plugin.invocations.model.llm import merge_llm_result_chunk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.llm.llm import AzureAIStudioLargeLanguageModel


def _chunk(*, tools=None, content=None, finish=None, usage=None):
    return StreamingChatCompletionsUpdate(
        {
            "id": "response",
            "model": "test",
            "created": 1,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": content, "tool_calls": tools},
                    "finish_reason": finish,
                }
            ],
            "usage": usage,
        }
    )


def _usage(model, credentials, prompt, completion):
    return LLMUsage.empty_usage().model_copy(
        update={
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        }
    )


def _stream(events, tail=b""):
    wire = (
        b"".join(
            b"data: " + json.dumps(event.as_dict()).encode() + b"\n\n"
            for event in events
        )
        + tail
    )
    return StreamingChatCompletions(httpx.Response(200, content=wire))


@pytest.mark.parametrize("with_indices", [False, True])
def test_stream_collects_same_function_calls_and_replays_their_results(with_indices):
    arguments = ['{ "city": "Paris", "n": 9007199254740993 }', '{"city":"Tokyo"}']
    ids = ["call_a", None if with_indices else "call_b"]

    def part(index, text, *, first=False):
        call = {"id": ids[index], "function": {"arguments": text}}
        if first:
            call["function"]["name"] = "weather"
        if with_indices:
            call["index"] = index
        return call

    events = [
        _chunk(content="Checking "),
        _chunk(
            tools=[
                part(0, arguments[0][:12], first=True),
                part(1, arguments[1][:8], first=True),
            ]
        ),
        _chunk(tools=[part(1, arguments[1][8:])]),
        _chunk(tools=[part(0, arguments[0][12:])], finish="tool_calls"),
        StreamingChatCompletionsUpdate(
            {
                "id": "response",
                "model": "test",
                "created": 1,
                "choices": [],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 3,
                    "total_tokens": 13,
                },
            }
        ),
    ]
    client = SimpleNamespace(complete=Mock(return_value=_stream(events)))
    llm = AzureAIStudioLargeLanguageModel([])
    llm._get_client = lambda credentials: client
    llm._calc_response_usage = _usage
    prompts = [UserPromptMessage(content="Weather in both cities?")]
    result = LLMResult(
        model="test",
        message=AssistantPromptMessage(content=""),
        usage=LLMUsage.empty_usage(),
    )
    chunks = list(llm._invoke("test", {}, prompts, {}, stream=True))
    for chunk in chunks:
        merge_llm_result_chunk(
            result, LLMResultChunk.model_validate_json(chunk.model_dump_json())
        )

    calls = result.message.tool_calls
    assert len(calls) == len({call.id for call in calls}) == 2
    assert all(call.id for call in calls)
    assert calls[0].id == "call_a"
    assert [call.function.arguments for call in calls] == arguments
    assert [call.function.name for call in calls] == ["weather", "weather"]
    assert all(not chunk.delta.message.tool_calls for chunk in chunks[:-1])
    assert result.message.content == "Checking "
    assert result.usage.total_tokens == 13

    prompts += [result.message] + [
        ToolPromptMessage(content=city, name="weather", tool_call_id=call.id)
        for city, call in zip(("Paris result", "Tokyo result"), calls)
    ]
    client.complete.return_value = iter([_chunk(content="done", finish="stop")])
    list(llm._invoke("test", {}, prompts, {}, stream=True))
    sent = client.complete.call_args.kwargs["messages"]
    assert [call["id"] for call in sent[1]["tool_calls"]] == [call.id for call in calls]
    assert [
        call["function"]["arguments"] for call in sent[1]["tool_calls"]
    ] == arguments
    assert [message["tool_call_id"] for message in sent[2:]] == [
        call.id for call in calls
    ]


def test_blocking_calls_without_ids_get_independent_ids():
    llm = AzureAIStudioLargeLanguageModel([])
    llm._calc_response_usage = _usage
    response = ChatCompletions(
        {
            "id": "response",
            "model": "test",
            "created": 1,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "weather", "arguments": "{}"},
                            }
                            for _ in range(2)
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
        }
    )
    result = llm._handle_non_stream_response(response, "test", [], {})
    assert len({call.id for call in result.message.tool_calls}) == 2
    assert all(call.id for call in result.message.tool_calls)


@pytest.mark.parametrize(
    ("arguments", "finish", "name", "tail"),
    [
        ("", None, "weather", b""),
        ('{"city":', None, "weather", b""),
        ('{"city":"Paris"}', None, "weather", b""),
        ("{}", "length", "weather", b""),
        ("{}", "content_filter", "weather", b""),
        ("{}", "unknown", "weather", b""),
        ("", "tool_calls", "weather", b""),
        ('{"city":', "tool_calls", "weather", b""),
        ("[]", "tool_calls", "weather", b""),
        ("null", "tool_calls", "weather", b""),
        ("{}", "tool_calls", "", b""),
        ('{"city":', None, "weather", b'data: {"id":'),
        ('{"city":', None, "weather", b'data: {"id":\n\n'),
    ],
)
def test_sse_rejects_unfinished_or_invalid_calls(arguments, finish, name, tail):
    events = [
        _chunk(
            tools=[
                {
                    "index": 0,
                    "id": "call_a",
                    "function": {"name": name, "arguments": arguments},
                }
            ]
        )
    ]
    if finish is not None:
        events.append(_chunk(finish=finish))
    llm = AzureAIStudioLargeLanguageModel([])
    response = llm._handle_stream_response(_stream(events, tail), "test", [], {})
    emitted = []
    with pytest.raises(InvokeError):
        for chunk in response:
            emitted.extend(chunk.delta.message.tool_calls)
    assert emitted == []


@pytest.mark.parametrize("finish", ["stop", "tool_calls"])
@pytest.mark.parametrize("arguments", ["{}", " { } "])
def test_sse_preserves_completed_zero_argument_calls(finish, arguments):
    events = [
        _chunk(
            tools=[
                {
                    "index": 0,
                    "id": "call_a",
                    "function": {"name": "ping", "arguments": arguments},
                }
            ]
        ),
        _chunk(finish=finish),
    ]
    llm = AzureAIStudioLargeLanguageModel([])
    chunks = list(llm._handle_stream_response(_stream(events), "test", [], {}))
    assert [
        call.function.arguments
        for chunk in chunks
        for call in chunk.delta.message.tool_calls
    ] == [arguments]
