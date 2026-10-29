import json

import httpx
import pytest
from dify_plugin.entities.model.llm import LLMUsage
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeError
from legacy.client import MaaSClient
from models.client import ArkClientV3
from models.llm.llm import VolcengineMaaSLargeLanguageModel


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("with_ids", [False, True])
def test_ark_same_function_calls_keep_separate_arguments_and_ids(
    monkeypatch, stream, with_ids
):
    calls = [
        {
            "type": "function",
            "function": {"name": "weather", "arguments": json.dumps({"city": city})},
        }
        for city in ("Tokyo", "Paris")
    ]
    if with_ids:
        for index, call in enumerate(calls):
            call["id"] = f"call-{index}"
    usage = {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}
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
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": calls,
                            },
                        }
                    ],
                    "usage": usage,
                },
            )
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
            for index, city in ((0, "Tokyo"), (1, "Paris"))
        ]
        frames = [
            {
                "id": "response",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "model",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"tool_calls": fragment},
                        "finish_reason": None,
                    }
                ],
            }
            for fragment in fragments
        ]
        frames.append(
            {
                "id": "response",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "model",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                "usage": usage,
            }
        )
        return httpx.Response(
            200,
            text="".join(f"data: {json.dumps(frame)}\n\n" for frame in frames)
            + "data: [DONE]\n\n",
        )

    client = ArkClientV3(
        api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(respond))
    )
    client.endpoint_id = "endpoint"
    monkeypatch.setattr(ArkClientV3, "from_credentials", lambda credentials: client)
    llm = VolcengineMaaSLargeLanguageModel([])
    llm._calc_response_usage = lambda *args, **kwargs: LLMUsage.empty_usage()
    prompts = [UserPromptMessage(content="Weather?")]
    try:
        result = llm._generate_v3("model", {}, prompts, {}, stream=stream)
        emitted = (
            [call for chunk in result for call in chunk.delta.message.tool_calls]
            if stream
            else result.message.tool_calls
        )
        assert len(emitted) == 2
        assert len({call.id for call in emitted}) == 2
        assert all(call.id for call in emitted)
        assert [json.loads(call.function.arguments) for call in emitted] == [
            {"city": "Tokyo"},
            {"city": "Paris"},
        ]
        if with_ids:
            assert [call.id for call in emitted] == ["call-0", "call-1"]
        prompts += [AssistantPromptMessage(content="", tool_calls=emitted)]
        prompts += [
            ToolPromptMessage(content="Sunny", tool_call_id=call.id)
            for call in reversed(emitted)
        ]
        replay = llm._generate_v3("model", {}, prompts, {}, stream=stream)
        if stream:
            list(replay)
        assert [
            message["tool_call_id"] for message in payloads[-1]["messages"][-2:]
        ] == [call.id for call in reversed(emitted)]
    finally:
        client.ark.close()


@pytest.mark.parametrize("with_ids", [False, True])
def test_legacy_ids_are_independent_of_function_names(monkeypatch, with_ids):
    calls = [
        {"type": "function", "function": {"name": "weather", "arguments": "{}"}}
        for _ in range(2)
    ]
    if with_ids:
        for index, call in enumerate(calls):
            call["id"] = f"call-{index}"
    response = {
        "choices": [{"message": {"content": "", "tool_calls": calls}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4},
    }
    client = MaaSClient("example.test", "region")
    payloads = []

    def request(endpoint_id, api, payload):
        payloads.append(payload)
        return response

    monkeypatch.setattr(client, "_request", request)
    monkeypatch.setattr(MaaSClient, "from_credential", lambda credentials: client)
    llm = VolcengineMaaSLargeLanguageModel([])
    llm._calc_response_usage = lambda *args, **kwargs: LLMUsage.empty_usage()
    first = llm._generate_v2("model", {}, [], {}, stream=False)
    assert len({call.id for call in first.message.tool_calls}) == 2
    assert all(call.id for call in first.message.tool_calls)
    if with_ids:
        assert [call.id for call in first.message.tool_calls] == ["call-0", "call-1"]
    llm._generate_v2(
        "model",
        {},
        [
            first.message,
            ToolPromptMessage(
                content="Sunny", tool_call_id=first.message.tool_calls[0].id
            ),
        ],
        {},
        stream=False,
    )
    assert payloads[-1]["messages"][-1]["name"] == "weather"


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
        (
            "{}",
            "weather",
            "tool_calls",
            'data: {"error":{"message":"failed"}}\n\n',
            False,
        ),
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
    client = ArkClientV3(
        api_key="test",
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, text=wire, headers={"content-type": "text/event-stream"}
                )
            )
        ),
    )
    client.endpoint_id = "endpoint"
    monkeypatch.setattr(ArkClientV3, "from_credentials", lambda credentials: client)
    llm = VolcengineMaaSLargeLanguageModel([])
    llm._calc_response_usage = lambda *args, **kwargs: LLMUsage.empty_usage()
    chunks = llm._generate_v3(
        "model", {}, [UserPromptMessage(content="Weather?")], {}, stream=True
    )
    try:
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
    finally:
        client.ark.close()
