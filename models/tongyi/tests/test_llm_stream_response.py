"""Exercise cumulative and incremental responses through the public SDK and SSE parser."""

import json
from pathlib import Path

import pytest
from dify_plugin.config.config import DifyPluginEnv
from dify_plugin.core.plugin_registration import PluginRegistration
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    ToolPromptMessage,
    UserPromptMessage,
)
from requests import Response


@pytest.fixture(scope="module")
def model():
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(Path(__file__).resolve().parents[1])
        registration = PluginRegistration(DifyPluginEnv())
    return registration.get_model_instance("tongyi", ModelType.LLM)


@pytest.fixture
def invoke(model, monkeypatch):
    requests = []
    frames = []

    def post(session, url, **kwargs):
        requests.append(json.loads(kwargs["data"]))
        assert kwargs["stream"] is True
        wire = []
        for fields, finish in frames:
            message = {"role": "assistant", "content": "", **fields}
            if "multimodal-generation" in url:
                content = message["content"]
                message["content"] = [{"text": content}] if content else []
            payload = {
                "request_id": "offline-stream",
                "output": {"choices": [{"message": message, "finish_reason": finish}]},
                "usage": {"input_tokens": 8, "output_tokens": 5},
            }
            wire.append(f"data: {json.dumps(payload)}\n\n")
        response = Response()
        response.status_code = 200
        response.encoding = "utf-8"
        response._content_consumed = True
        response.headers["content-type"] = "text/event-stream"
        response._content = "".join(wire).encode()
        return response

    monkeypatch.setattr("requests.Session.post", post)

    def run(name, response_frames, *, with_tools=True, thinking=True, history=None):
        frames[:] = response_frames
        tool = PromptMessageTool(
            name="weather",
            description="Get the weather",
            parameters={"type": "object", "properties": {"city": {"type": "string"}}},
        )
        chunks = list(
            model.invoke(
                name,
                {"dashscope_api_key": "test-key"},
                history or [UserPromptMessage(content="What is the weather?")],
                {"enable_thinking": thinking},
                tools=[tool] if with_tools else None,
                stream=True,
            )
        )
        assert len([chunk for chunk in chunks if chunk.delta.finish_reason]) == 1
        assert chunks[-1].delta.finish_reason == response_frames[-1][1]
        assert chunks[-1].delta.usage.prompt_tokens == 8
        assert chunks[-1].delta.usage.completion_tokens == 5
        return "".join(chunk.delta.message.content for chunk in chunks), chunks, requests

    return run


@pytest.mark.parametrize(
    "name,with_tools",
    [
        ("qwen3.6-flash", True),
        ("glm-5.1", True),
        ("qwen3.8-flash", True),
        ("deepseek-v4-pro", True),
        ("qwen3.6-flash", False),
        ("glm-5.1", False),
    ],
)
@pytest.mark.parametrize(
    "frames,expected",
    [
        (
            [
                ({"reasoning_content": "R1"}, "null"),
                ({}, "null"),
                ({"reasoning_content": "R2"}, "null"),
                ({"content": "A1"}, "null"),
                ({"content": "A2"}, "null"),
                ({}, "stop"),
            ],
            "<think>\nR1R2\n</think>A1A2",
        ),
        (
            [
                ({"reasoning_content": "R1"}, "null"),
                ({"reasoning_content": "R2", "content": "A1"}, "null"),
                ({"content": "A2"}, "stop"),
            ],
            "<think>\nR1R2\n</think>A1A2",
        ),
        (
            [({"reasoning_content": "R1"}, "null"), ({"content": "A1"}, "stop")],
            "<think>\nR1\n</think>A1",
        ),
        (
            [({"reasoning_content": "R1"}, "null"), ({"reasoning_content": "R2"}, "length")],
            "<think>\nR1R2\n</think>",
        ),
        (
            [({"reasoning_content": "R1", "content": "A1"}, "stop")],
            "<think>\nR1\n</think>A1",
        ),
    ],
    ids=["empty-middle", "mixed-transition", "final-answer", "final-reasoning", "single-frame"],
)
def test_stream_preserves_reasoning_and_answer(invoke, name, with_tools, frames, expected):
    text, _, _ = invoke(name, frames, with_tools=with_tools)
    assert text == expected


@pytest.mark.parametrize("name", ["qwen3.6-flash", "glm-5.1"])
def test_stream_without_thinking(invoke, name):
    text, _, _ = invoke(
        name,
        [({"content": "A1"}, "null"), ({"content": "A2"}, "null"), ({}, "stop")],
        thinking=False,
    )
    assert text == "A1A2"


@pytest.mark.parametrize("name", ["qwen3.6-flash", "glm-5.1", "qwen3.8-flash", "deepseek-v4-pro"])
def test_reasoning_tool_round_trip(invoke, name):
    frames = [({"reasoning_content": "R1"}, "null"), ({"reasoning_content": "R2"}, "null")]
    for index, (tool_name, arguments) in enumerate([("weather", '{"city":'), ("", '"Paris"}')]):
        frames.append(
            (
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_weather" if index == 0 else "",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": arguments},
                        }
                    ]
                },
                "null",
            )
        )
    frames.append(({}, "tool_calls"))
    text, chunks, _ = invoke(name, frames)
    assert text == "<think>\nR1R2\n</think>"
    calls = chunks[-1].delta.message.tool_calls
    assert len(calls) == 1
    assert calls[0].function.name == "weather"
    assert json.loads(calls[0].function.arguments) == {"city": "Paris"}

    text, _, requests = invoke(
        name,
        [({"reasoning_content": "R3"}, "null"), ({"content": "Sunny"}, "stop")],
        history=[
            UserPromptMessage(content="What is the weather?"),
            AssistantPromptMessage(content=text, tool_calls=calls),
            ToolPromptMessage(content="Sunny", tool_call_id=calls[0].id),
        ],
    )
    assert text == "<think>\nR3\n</think>Sunny"
    assert len(requests) == 2
    assert requests[-1]["input"]["messages"][-1]["content"] == "Sunny"
