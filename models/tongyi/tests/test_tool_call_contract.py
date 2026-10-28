import json

import pytest
import requests
from dashscope.api_entities.http_request import HttpRequest
from dashscope.api_entities.dashscope_response import (
    DashScopeAPIResponse,
    GenerationResponse,
)
from dify_plugin.entities.model.llm import LLMUsage
from dify_plugin.errors.model import InvokeError
from dify_plugin.entities.model.message import AssistantPromptMessage, ToolPromptMessage
from models.llm.llm import TongyiLargeLanguageModel


def response(calls, finish_reason="null"):
    return GenerationResponse.from_api_response(
        DashScopeAPIResponse(
            status_code=200,
            output={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": calls,
                        },
                        "finish_reason": finish_reason,
                    }
                ]
            },
            usage={"input_tokens": 10, "output_tokens": 4},
        )
    )


@pytest.mark.parametrize("incremental", [False, True])
@pytest.mark.parametrize("with_ids", [False, True])
def test_complete_tool_calls_are_emitted_once_with_distinct_ids(incremental, with_ids):
    calls = [
        {
            "index": index,
            "type": "function",
            "function": {"name": "weather", "arguments": '{"city":"'},
        }
        for index in range(2)
    ]
    if with_ids:
        for index, call in enumerate(calls):
            call["id"] = f"call-{index}"
    continuation = [
        {
            "index": index,
            "function": {
                "arguments": f'{city}"}}' if incremental else json.dumps({"city": city})
            },
        }
        for index, city in enumerate(("Tokyo", "Paris"))
    ]
    llm = TongyiLargeLanguageModel([])
    llm._calc_response_usage = lambda *args: LLMUsage.empty_usage()
    chunks = list(
        llm._handle_generate_stream_response(
            "qwen",
            {},
            iter(
                [
                    response(calls),
                    response(continuation),
                    response([], "tool_calls"),
                    response([], "stop"),
                ]
            ),
            [],
            incremental,
        )
    )
    emitted = [call for chunk in chunks for call in chunk.delta.message.tool_calls]
    assert len(emitted) == 2
    assert len({call.id for call in emitted}) == 2
    assert all(call.id for call in emitted)
    assert [json.loads(call.function.arguments) for call in emitted] == [
        {"city": "Tokyo"},
        {"city": "Paris"},
    ]
    if with_ids:
        assert [call.id for call in emitted] == ["call-0", "call-1"]
    replay = llm._convert_prompt_messages_to_tongyi_messages(
        [
            AssistantPromptMessage(content="", tool_calls=emitted),
            ToolPromptMessage(content="Sunny", tool_call_id=emitted[0].id),
        ]
    )
    assert replay[1]["tool_call_id"] == emitted[0].id


def test_blocking_calls_without_ids_receive_distinct_ids():
    llm = TongyiLargeLanguageModel([])
    llm._calc_response_usage = lambda *args: LLMUsage.empty_usage()
    calls = [
        {"type": "function", "function": {"name": "weather", "arguments": "{}"}}
        for _ in range(2)
    ]
    result = llm._handle_generate_response(
        "qwen", {}, response(calls, "tool_calls"), []
    )
    assert len({call.id for call in result.message.tool_calls}) == 2
    assert all(call.id for call in result.message.tool_calls)


@pytest.mark.parametrize(
    "arguments,name,finish_reason,tail,succeeds",
    [
        (' { "city" : "Paris" } ', "weather", "tool_calls", "", True),
        ("{}", "weather", "stop", "", True),
        ("{ }", "weather", "tool_calls", "", True),
        ('{"city":', "weather", None, "", False),
        ("{}", "weather", None, "", False),
        ("", "weather", None, "", False),
        ('{"city":', "weather", "length", "", False),
        ("{}", "weather", "length", "", False),
        ("{}", "weather", "content_filter", "", False),
        ("", "weather", "tool_calls", "", False),
        ('{"city":', "weather", "tool_calls", "", False),
        ("[]", "weather", "tool_calls", "", False),
        ("null", "weather", "tool_calls", "", False),
        ("{}", "", "tool_calls", "", False),
        ("{}", "   ", "tool_calls", "", False),
        ("{}", "weather", None, 'data: {"broken":', False),
        ("{}", "weather", None, 'data: {"broken":\n\n', False),
        ("{}", "weather", "tool_calls", 'data: {"broken":\n\n', False),
        ("{}", "weather", "tool_calls", 'event:error\nstatus:500\ndata: {"code":"InternalError","message":"failed"}\n\n', False),
    ],
)
def test_sse_tool_calls_require_complete_objects_and_success(
    monkeypatch, arguments, name, finish_reason, tail, succeeds
):
    call = {
        "index": 0,
        "id": "call-0",
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }
    def frame(calls, reason="null"):
        return {
            "output": {
                "choices": [{"message": {"role": "assistant", "content": "", "tool_calls": calls},
                             "finish_reason": reason}]
            },
            "usage": {"input_tokens": 10, "output_tokens": 4},
        }

    frames = [frame([call])]
    if finish_reason:
        frames.append(frame([], finish_reason))
    response = requests.Response()
    response.status_code = 200
    response.headers["content-type"] = "text/event-stream"
    response._content = ("".join(f"data: {json.dumps(frame)}\n\n" for frame in frames) + tail).encode()
    response._content_consumed = True
    request = HttpRequest("https://example.test/", "test", "POST", stream=True)
    decoded = (GenerationResponse.from_api_response(item) for item in request._handle_response(response))
    llm = TongyiLargeLanguageModel([])
    llm._calc_response_usage = lambda *args: LLMUsage.empty_usage()
    chunks = llm._handle_generate_stream_response("qwen", {}, decoded, [], True)

    emitted = []
    if succeeds:
        for chunk in chunks:
            emitted.extend(chunk.delta.message.tool_calls)
        assert len(emitted) == 1
        assert emitted[0].id == "call-0"
        assert emitted[0].function.name == name
        assert emitted[0].function.arguments == arguments
    else:
        with pytest.raises(InvokeError):
            for chunk in chunks:
                emitted.extend(chunk.delta.message.tool_calls)
        assert emitted == []
