import json

import pytest
import requests
from dify_plugin.entities.model.llm import LLMUsage
from dify_plugin.errors.model import InvokeError
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from models.llm import llm as module


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("with_ids", [False, True])
@pytest.mark.parametrize("legacy", [False, True])
def test_tool_calls_keep_their_arguments_ids_and_results(
    monkeypatch, stream, with_ids, legacy
):
    count = 1 if legacy else 2
    calls = [
        {
            "type": "function",
            "function": {"name": "weather", "arguments": json.dumps({"city": city})},
        }
        for city in ("Tokyo", "Paris")[:count]
    ]
    if with_ids and not legacy:
        for index, call in enumerate(calls):
            call["id"] = f"call-{index}"
    usage = {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}
    payloads = []

    def respond(url, **kwargs):
        payloads.append(kwargs["json"])
        if kwargs["stream"]:
            fragments = [
                [
                    {
                        "index": index,
                        **call,
                        "function": {"name": "weather", "arguments": '{"city":"'},
                    }
                ]
                for index, call in enumerate(calls)
            ]
            fragments += [
                [{"index": index, "function": {"arguments": f'{city}"}}'}}]
                for index, city in reversed(list(enumerate(("Tokyo", "Paris")[:count])))
            ]
            frames = [
                {
                    "model": "model",
                    "choices": [
                        {
                            "delta": {"function_call": fragment[0]["function"]}
                            if legacy
                            else {"tool_calls": fragment},
                            "finish_reason": None,
                        }
                    ],
                }
                for fragment in fragments
            ]
            frames.append(
                {
                    "model": "model",
                    "choices": [{"delta": {}, "finish_reason": "tool_calls"}],
                    "usage": usage,
                }
            )
            body = (
                "".join(f"data: {json.dumps(frame)}\n\n" for frame in frames)
                + "data: [DONE]\n\n"
            )
        else:
            message = (
                {"content": None, "function_call": calls[0]["function"]}
                if legacy
                else {"content": None, "tool_calls": calls}
            )
            body = json.dumps(
                {"model": "model", "choices": [{"message": message}], "usage": usage}
            )
        response = requests.Response()
        response.status_code = 200
        response.encoding = "utf-8"
        response._content = body.encode()
        response._content_consumed = True
        return response

    monkeypatch.setattr(module.requests, "post", respond)
    llm = module.GiteeAILargeLanguageModel([])
    llm._calc_response_usage = lambda *args: LLMUsage.empty_usage()
    credentials = {
        "mode": "chat",
        "endpoint_url": "https://example.test/v1",
        "function_calling_type": "function_call" if legacy else "tool_call",
    }
    prompts = [UserPromptMessage(content="Weather?")]
    result = llm._generate("model", credentials, prompts, {}, stream=stream)
    emitted = (
        [call for chunk in result for call in chunk.delta.message.tool_calls]
        if stream
        else result.message.tool_calls
    )
    assert len(emitted) == count
    assert len({call.id for call in emitted}) == count
    assert all(call.id for call in emitted)
    assert [json.loads(call.function.arguments) for call in emitted] == [
        {"city": city} for city in ("Tokyo", "Paris")[:count]
    ]
    if with_ids and not legacy:
        assert [call.id for call in emitted] == [
            f"call-{index}" for index in range(count)
        ]
    prompts += [AssistantPromptMessage(content="", tool_calls=emitted)]
    prompts += [
        ToolPromptMessage(content=call.function.arguments, tool_call_id=call.id)
        for call in reversed(emitted)
    ]
    replay = llm._generate("model", credentials, prompts, {}, stream=False)
    assert replay.message.tool_calls
    if legacy:
        assert payloads[-1]["messages"][-1]["name"] == "weather"
    else:
        assert [
            message["tool_call_id"] for message in payloads[-1]["messages"][-count:]
        ] == [call.id for call in reversed(emitted)]


@pytest.mark.parametrize(
    "arguments,name,finish_reason,tail,succeeds",
    [
        (' { "city" : "Paris" } ', "weather", "tool_calls", "", True),
        ("{}", "weather", "stop", "", True),
        ("{ }", "weather", "tool_calls", "", True),
        ("{}", "weather", "function_call", "", True),
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
        ("{}", "weather", "tool_calls", 'data: {"error":{"message":"failed"}}\n\n', False),
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
    def frame(delta, reason=None):
        return {
            "id": "response",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "model",
            "choices": [{"index": 0, "delta": delta, "finish_reason": reason}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        }

    frames = [frame({"tool_calls": [call]})]
    if finish_reason:
        frames.append(frame({}, finish_reason))
    wire = "".join(f"data: {json.dumps(frame)}\n\n" for frame in frames) + tail
    response = requests.Response()
    response.status_code = 200
    response.encoding = "utf-8"
    response._content = wire.encode()
    response._content_consumed = True
    llm = module.GiteeAILargeLanguageModel([])
    llm._calc_response_usage = lambda *args: LLMUsage.empty_usage()
    chunks = llm._handle_generate_stream_response(
        "model", {"mode": "chat", "function_calling_type": "tool_call"}, response, []
    )

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
