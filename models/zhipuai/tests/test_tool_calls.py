import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMUsage
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeError
from dify_plugin.invocations.model.llm import merge_llm_result_chunk
from zai import ZhipuAiClient
from zai.types.chat import ChatCompletionChunk, Completion

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.llm.llm import ZhipuAILargeLanguageModel


def _chunk(delta=None, *, finish=None, usage=None):
    return ChatCompletionChunk.model_validate(
        {
            "id": "response",
            "model": "glm-4",
            "created": 1,
            "extra_json": {},
            "choices": []
            if delta is None
            else [{"index": 0, "delta": delta, "finish_reason": finish}],
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
            b"data: " + event.model_dump_json().encode() + b"\n\n" for event in events
        )
        + tail
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, content=wire, headers={"content-type": "text/event-stream"}
        )
    )
    with httpx.Client(transport=transport) as http_client:
        client = ZhipuAiClient(api_key="test", http_client=http_client)
        yield from client.chat.completions.create(
            model="glm-4", messages=[{"role": "user", "content": "test"}], stream=True
        )


def test_stream_collects_parallel_fragments_and_replays_the_results():
    arguments = ['{ "city": "Paris", "n": 9007199254740993 }', '{"city":"Tokyo"}']
    events = [
        _chunk({"content": "Checking "}),
        _chunk(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_a",
                        "type": "function",
                        "function": {"name": "weather", "arguments": arguments[0][:12]},
                    },
                    {
                        "index": 1,
                        "type": "function",
                        "function": {"name": "weather", "arguments": arguments[1][:8]},
                    },
                ]
            }
        ),
        _chunk(
            {"tool_calls": [{"index": 1, "function": {"arguments": arguments[1][8:]}}]}
        ),
        _chunk(
            {
                "tool_calls": [
                    {"index": 0, "function": {"arguments": arguments[0][12:]}}
                ]
            },
            finish="tool_calls",
        ),
        _chunk(usage={"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13}),
    ]
    complete = Mock(return_value=_stream(events))
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=complete))
    )
    llm = ZhipuAILargeLanguageModel([])
    llm._calc_response_usage = _usage
    prompts = [UserPromptMessage(content="Weather in both cities?")]
    result = LLMResult(
        model="glm-4",
        message=AssistantPromptMessage(content=""),
        usage=LLMUsage.empty_usage(),
    )
    with patch("models.llm.llm.ZhipuAiClient", return_value=client):
        chunks = list(
            llm._invoke("glm-4", {"api_key": "test"}, prompts, {}, stream=True)
        )
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
        complete.return_value = iter([_chunk({"content": "done"}, finish="stop")])
        list(llm._invoke("glm-4", {"api_key": "test"}, prompts, {}, stream=True))

    sent = complete.call_args.kwargs["messages"]
    assert [call["id"] for call in sent[1]["tool_calls"]] == [call.id for call in calls]
    assert [
        call["function"]["arguments"] for call in sent[1]["tool_calls"]
    ] == arguments
    assert [message["tool_call_id"] for message in sent[2:]] == [
        call.id for call in calls
    ]


def test_blocking_calls_without_ids_get_independent_ids():
    llm = ZhipuAILargeLanguageModel([])
    llm._calc_response_usage = _usage
    response = Completion.model_validate(
        {
            "id": "response",
            "model": "glm-4",
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
    result = llm._handle_generate_response("glm-4", {}, None, response, [])
    assert len({call.id for call in result.message.tool_calls}) == 2
    assert all(call.id for call in result.message.tool_calls)


@pytest.mark.parametrize(
    ("arguments", "finish", "name", "tail"),
    [
        ("", None, "weather", b""),
        ('{"city":', None, "weather", b""),
        ('{"city":"Paris"}', None, "weather", b""),
        ("{}", "length", "weather", b""),
        ("{}", "sensitive", "weather", b""),
        ("{}", "network_error", "weather", b""),
        ("{}", "model_context_window_exceeded", "weather", b""),
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
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_a",
                        "type": "function",
                        "function": {"name": name, "arguments": arguments},
                    }
                ]
            }
        )
    ]
    if finish is not None:
        events.append(_chunk({}, finish=finish))
    llm = ZhipuAILargeLanguageModel([])
    response = llm._handle_generate_stream_response(
        "glm-4", {}, None, _stream(events, tail), []
    )
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
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_a",
                        "type": "function",
                        "function": {"name": "ping", "arguments": arguments},
                    }
                ]
            }
        ),
        _chunk({}, finish=finish),
    ]
    llm = ZhipuAILargeLanguageModel([])
    chunks = list(
        llm._handle_generate_stream_response("glm-4", {}, None, _stream(events), [])
    )
    assert [
        call.function.arguments
        for chunk in chunks
        for call in chunk.delta.message.tool_calls
    ] == [arguments]
