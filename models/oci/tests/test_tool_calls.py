import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMUsage
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeError
from dify_plugin.invocations.model.llm import merge_llm_result_chunk
from oci._vendor.sseclient import SSEClient
from oci.base_client import BaseClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.llm.llm import Convertor, OCILargeLanguageModel

ARGUMENTS = ['{ "city": "Paris", "n": 9007199254740993 }', '{"city":"Tokyo"}']
USAGE = {"promptTokens": 10, "completionTokens": 3, "totalTokens": 13}


def _calls(vendor):
    if vendor == "cohere":
        return [
            {"name": "weather", "parameters": json.loads(arguments)}
            for arguments in ARGUMENTS
        ]
    return [
        {"id": call_id, "type": "FUNCTION", "name": "weather", "arguments": arguments}
        for call_id, arguments in zip(("call_a", "call_b"), ARGUMENTS)
    ]


def _response(vendor, *, with_tools):
    calls = _calls(vendor) if with_tools else []
    if vendor == "cohere":
        chat = {
            "apiFormat": "COHERE",
            "finishReason": "COMPLETE",
            "text": "" if with_tools else "done",
            "toolCalls": calls,
            "usage": USAGE,
        }
    else:
        chat = {
            "apiFormat": "GENERIC",
            "choices": [
                {
                    "finishReason": "tool_calls" if with_tools else "stop",
                    "message": {
                        "role": "ASSISTANT",
                        "content": [
                            {"type": "TEXT", "text": "" if with_tools else "done"}
                        ],
                        "toolCalls": calls,
                    },
                }
            ],
            "usage": USAGE,
        }
    return {"modelId": vendor + ".test", "chatResponse": chat}


def _stream(vendor):
    if vendor == "cohere":
        events = [
            {"finishReason": "COMPLETE", "toolCalls": _calls(vendor), "usage": USAGE}
        ]
    else:
        events = [
            {
                "message": {
                    "toolCalls": [
                        {
                            "id": "call_a",
                            "name": "weather",
                            "arguments": ARGUMENTS[0][:12],
                        }
                    ]
                }
            },
            {
                "message": {
                    "toolCalls": [
                        {
                            "id": "call_b",
                            "name": "weather",
                            "arguments": ARGUMENTS[1][:8],
                        }
                    ]
                }
            },
            {"message": {"toolCalls": [{"arguments": ARGUMENTS[1][8:]}]}},
            {
                "message": {
                    "toolCalls": [{"id": "call_a", "arguments": ARGUMENTS[0][12:]}]
                }
            },
            {"finishReason": "tool_calls", "usage": USAGE},
        ]
    return _sse_stream(events)


def _sse_stream(events, tail=b""):
    wire = (
        b"".join(b"data: " + json.dumps(event).encode() + b"\n\n" for event in events)
        + tail
    )
    response = requests.Response()
    response.status_code = 200
    response.headers["content-type"] = "text/event-stream"
    response.raw = io.BytesIO(wire)
    return SimpleNamespace(data=SSEClient(response))


def _usage(model, credentials, prompt, completion):
    return LLMUsage.empty_usage().model_copy(
        update={
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        }
    )


@pytest.mark.parametrize("vendor", ["cohere", "meta"])
@pytest.mark.parametrize("stream", [False, True])
def test_same_function_calls_round_trip_through_native_requests(vendor, stream):
    llm = OCILargeLanguageModel([])
    llm._get_oci_credentials = lambda credentials: {}
    llm.get_model_schema = lambda **kwargs: SimpleNamespace(
        features=["multi-tool-call"]
    )
    llm._calc_response_usage = _usage
    base_client = object.__new__(BaseClient)
    base_client.complex_type_mappings = {}
    first = (
        _stream(vendor)
        if stream
        else SimpleNamespace(
            data=SimpleNamespace(text=json.dumps(_response(vendor, with_tools=True)))
        )
    )
    final = SimpleNamespace(
        data=SimpleNamespace(text=json.dumps(_response(vendor, with_tools=False)))
    )
    base_client.call_api = Mock(side_effect=[first, final])
    client = SimpleNamespace(base_client=base_client)
    prompts = [UserPromptMessage(content="Weather in both cities?")]
    with patch(
        "models.llm.llm.oci.generative_ai_inference.GenerativeAiInferenceClient",
        return_value=client,
    ):
        response = llm._generate(vendor + ".test", {}, prompts, {}, stream=stream)
        if stream:
            result = LLMResult(
                model=vendor + ".test",
                message=AssistantPromptMessage(content=""),
                usage=LLMUsage.empty_usage(),
            )
            chunks = list(response)
            for chunk in chunks:
                merge_llm_result_chunk(
                    result, LLMResultChunk.model_validate_json(chunk.model_dump_json())
                )
            assert all(not chunk.delta.message.tool_calls for chunk in chunks[:-1])
        else:
            result = response

        calls = result.message.tool_calls
        assert len(calls) == len({call.id for call in calls}) == 2
        assert all(call.id for call in calls)
        assert [call.function.name for call in calls] == ["weather", "weather"]
        assert [json.loads(call.function.arguments) for call in calls] == [
            json.loads(arguments) for arguments in ARGUMENTS
        ]
        if vendor == "meta":
            assert [call.id for call in calls] == ["call_a", "call_b"]
            assert [call.function.arguments for call in calls] == ARGUMENTS
        assert result.usage.total_tokens == 13

        prompts += [result.message] + [
            ToolPromptMessage(content=city, name="weather", tool_call_id=call.id)
            for city, call in zip(("Paris result", "Tokyo result"), calls)
        ]
        assert (
            llm._generate(
                vendor + ".test", {}, prompts, {}, stream=False
            ).message.content
            == "done"
        )

    request = json.loads(base_client.call_api.call_args.kwargs["body"])["chatRequest"]
    if vendor == "cohere":
        results = request["toolResults"]
        assert len(results) == 2
        assert [result["call"]["name"] for result in results] == ["weather", "weather"]
        assert [result["call"]["parameters"] for result in results] == [
            json.loads(arguments) for arguments in ARGUMENTS
        ]
        assert [result["outputs"] for result in results] == [
            [{"tool_results": "Paris result"}],
            [{"tool_results": "Tokyo result"}],
        ]
        assert len(request["chatHistory"]) == 2
    else:
        messages = request["messages"]
        assert [call["id"] for call in messages[1]["toolCalls"]] == [
            call.id for call in calls
        ]
        assert [call["arguments"] for call in messages[1]["toolCalls"]] == ARGUMENTS
        assert [message["toolCallId"] for message in messages[2:]] == [
            call.id for call in calls
        ]


def test_cohere_rejects_unmatched_tool_results():
    with pytest.raises(ValueError, match="Unknown tool call ID"):
        Convertor()._parse_prompt_message_to_cohere(
            ToolPromptMessage(content="result", name="weather", tool_call_id="missing")
        )


@pytest.mark.parametrize(
    ("arguments", "finish", "name", "tail"),
    [
        ("", None, "weather", b""),
        ('{"city":', None, "weather", b""),
        ('{"city":"Paris"}', None, "weather", b""),
        ("{}", "length", "weather", b""),
        ("{}", "unknown", "weather", b""),
        ("", "tool_calls", "weather", b""),
        ('{"city":', "tool_calls", "weather", b""),
        ("[]", "tool_calls", "weather", b""),
        ("null", "tool_calls", "weather", b""),
        ("{}", "tool_calls", "", b""),
        ('{"city":', None, "weather", b'data: {"message":'),
    ],
)
def test_generic_sse_rejects_unfinished_or_invalid_calls(arguments, finish, name, tail):
    events = [
        {
            "message": {
                "toolCalls": [
                    {
                        "id": "call_a",
                        "name": name,
                        "arguments": arguments,
                    }
                ]
            }
        }
    ]
    if finish is not None:
        events.append({"finishReason": finish})
    llm = OCILargeLanguageModel([])
    response = llm._handle_generate_stream_response(
        "meta.test", {}, _sse_stream(events, tail), []
    )
    emitted = []
    with pytest.raises(InvokeError):
        for chunk in response:
            emitted.extend(chunk.delta.message.tool_calls)
    assert emitted == []


@pytest.mark.parametrize(
    ("parameters", "finish", "name"),
    [
        ({}, None, "ping"),
        ({}, "MAX_TOKENS", "ping"),
        ({}, "ERROR", "ping"),
        ({}, "ERROR_LIMIT", "ping"),
        ({}, "ERROR_TOXIC", "ping"),
        ({}, "USER_CANCEL", "ping"),
        ({}, "tool_calls", "ping"),
        ({}, "COMPLETE", ""),
        ([], "COMPLETE", "ping"),
        (None, "COMPLETE", "ping"),
    ],
)
def test_cohere_sse_rejects_unfinished_or_invalid_calls(parameters, finish, name):
    events = [
        {
            "toolCalls": [{"name": name, "parameters": parameters}],
            "finishReason": finish,
        }
    ]
    llm = OCILargeLanguageModel([])
    response = llm._handle_generate_stream_response(
        "cohere.test", {}, _sse_stream(events), []
    )
    emitted = []
    with pytest.raises(InvokeError):
        for chunk in response:
            emitted.extend(chunk.delta.message.tool_calls)
    assert emitted == []


@pytest.mark.parametrize("finish", ["stop", "tool_calls"])
@pytest.mark.parametrize("arguments", ["{}", " { } "])
def test_generic_sse_preserves_completed_zero_argument_calls(finish, arguments):
    events = [
        {
            "message": {
                "toolCalls": [{"id": "call_a", "name": "ping", "arguments": arguments}]
            }
        },
        {"finishReason": finish},
    ]
    llm = OCILargeLanguageModel([])
    chunks = list(
        llm._handle_generate_stream_response("meta.test", {}, _sse_stream(events), [])
    )
    assert [
        call.function.arguments
        for chunk in chunks
        for call in chunk.delta.message.tool_calls
    ] == [arguments]


def test_cohere_sse_accepts_completed_zero_argument_call():
    events = [
        {"toolCalls": [{"name": "ping", "parameters": {}}], "finishReason": "COMPLETE"}
    ]
    llm = OCILargeLanguageModel([])
    chunks = list(
        llm._handle_generate_stream_response("cohere.test", {}, _sse_stream(events), [])
    )
    assert [
        call.function.arguments
        for chunk in chunks
        for call in chunk.delta.message.tool_calls
    ] == ["{}"]
