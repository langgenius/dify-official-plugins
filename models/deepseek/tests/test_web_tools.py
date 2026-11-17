import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    UserPromptMessage,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.llm.llm import DeepseekLargeLanguageModel


def _llm(model="deepseek-flash"):
    schema = yaml.safe_load(
        (ROOT / "models/llm" / f"{model}.yaml").read_text(encoding="utf-8")
    )
    return DeepseekLargeLanguageModel(
        model_schemas=[AIModelEntity.model_validate(schema)]
    )


@pytest.mark.parametrize(
    "extension",
    [
        {"deepseek_web_search": True},
        {"deepseek_read_url": True},
        {"safety_check": "high"},
        {"safety_check": {"level": "high"}},
        {"title": True},
        {"title": {"enabled": True}},
    ],
)
@pytest.mark.parametrize("client_tools", [False, True])
def test_extensions_with_client_tools_require_thinking(extension, client_tools):
    tools = (
        [PromptMessageTool(name="local_tool", description="Local", parameters={})]
        if client_tools
        else None
    )
    with patch("requests.post", return_value=Mock(status_code=200)) as post:
        _llm()._invoke(
            "deepseek-flash",
            {"api_key": "test"},
            [UserPromptMessage(content="Hi")],
            {"thinking": False, "temperature": 0.7, **extension},
            tools=tools,
        )
    request = json.loads(post.call_args.kwargs["data"])
    assert request["thinking"] == {"type": "enabled" if client_tools else "disabled"}, (
        "tools: client tools can only be used together with web tools, safety_check or title in thinking mode"
    )
    assert ("temperature" in request) is not client_tools
    assert (
        any(tool["type"] == "function" for tool in request.get("tools", []))
    ) is client_tools


@pytest.mark.parametrize(
    "parameters",
    [
        {"title": False},
        {"title": {"enabled": False}},
        {"safety_check": "low"},
        {"safety_check": {"level": "low"}},
        {
            "title": False,
            "safety_check": "low",
            "deepseek_web_search": False,
            "deepseek_read_url": False,
        },
    ],
)
def test_inactive_extensions_are_omitted_without_forcing_thinking(parameters):
    with patch("requests.post", return_value=Mock(status_code=200)) as post:
        _llm()._invoke(
            "deepseek-flash",
            {"api_key": "test"},
            [UserPromptMessage(content="Hi")],
            {"thinking": False, **parameters},
            tools=[
                PromptMessageTool(name="local_tool", description="Local", parameters={})
            ],
        )
    request = json.loads(post.call_args.kwargs["data"])
    assert "title" not in request
    assert "safety_check" not in request
    assert request["thinking"] == {"type": "disabled"}
    assert request["tools"][0]["type"] == "function"


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("thinking", [False, True])
@pytest.mark.parametrize(
    "web_search,read_url", [(True, False), (False, True), (True, True), (False, False)]
)
def test_server_tools_request_response_and_history(
    stream, thinking, web_search, read_url
):
    llm = _llm()
    steps = [
        {
            "index": 0,
            "reasoning_content": "First reasoning step.",
            "calls": [
                {
                    "index": 0,
                    "id": "srvtoolu_1",
                    "type": "deepseek_read_url",
                    "kind": "read_link",
                    "action": {"type": "read_link", "url": "https://example.com"},
                    "status": "completed",
                    "page": {"url": "https://example.com", "title": "Example"},
                    "signature": "encrypted-exactly+/=",
                }
            ],
        }
    ]
    annotations = [
        {
            "type": "url_citation",
            "url_citation": {
                "start_index": 0,
                "end_index": 6,
                "title": "Example",
                "url": "https://example.com",
            },
        }
    ]
    metadata = {
        "server_tool_calls": steps,
        "annotations": annotations,
        "title": "Example title",
    }
    reasoning = "Final reasoning." if thinking else ""
    function_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "local_tool", "arguments": "{}"},
        }
    ]
    usage = {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
        "server_tool_use": {"tool_search": 1, "tool_fetch": 1, "tool_image_search": 0},
    }
    response = Mock(status_code=200)
    response.json.return_value = {
        "model": "deepseek-flash",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Answer",
                    "reasoning_content": reasoning,
                    "tool_calls": function_calls,
                    **metadata,
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": usage,
    }
    events = [
        {
            "choices": [
                {
                    "delta": {
                        "reasoning_content": "First reasoning step." if thinking else ""
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {},
                    "server_tool_event": {"type": "step_reasoning_done", "step": 0},
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {},
                    "server_tool_event": {
                        "type": "call_completed",
                        "step": 0,
                        "call": {},
                    },
                }
            ]
        },
        {"choices": [{"delta": {"reasoning_content": reasoning}}]},
        {"choices": [{"delta": {"content": "Answer", "tool_calls": function_calls}}]},
        {
            "choices": [{"delta": metadata, "finish_reason": "tool_calls"}],
            "usage": usage,
        },
    ]
    response.iter_lines.return_value = [
        ": keep-alive",
        *["data: " + json.dumps(event) for event in events],
        "data: [DONE]",
    ]
    with patch("requests.post", return_value=response) as post:
        chunks = list(
            llm.invoke(
                "deepseek-flash",
                {"api_key": "test"},
                [UserPromptMessage(content="Read https://example.com")],
                {
                    "thinking": thinking,
                    "deepseek_web_search": web_search,
                    "deepseek_read_url": read_url,
                    "safety_check": "high",
                    "title": True,
                },
                tools=[
                    PromptMessageTool(
                        name="local_tool", description="Local", parameters={}
                    )
                ],
                stream=stream,
            )
        )
    request = json.loads(post.call_args.kwargs["data"])
    expected_tools = [
        name
        for name, enabled in (
            ("deepseek_web_search", web_search),
            ("deepseek_read_url", read_url),
        )
        if enabled
    ]
    assert [tool["type"] for tool in request["tools"]] == [*expected_tools, "function"]
    assert "deepseek_web_search" not in request
    assert "deepseek_read_url" not in request
    assert "tool_choice" not in request
    assert request["safety_check"] == {"level": "high"}
    assert request["title"] == {"enabled": True}
    assert request["thinking"] == {"type": "enabled"}
    terminal = chunks[-1].delta
    assert terminal.usage.total_tokens == 120
    assert terminal.message.opaque_body == {
        **metadata,
        "reasoning_content": reasoning,
        "server_tool_use": usage["server_tool_use"],
    }
    # Simulate serialized Dify history, preserving opaque metadata on the final chunk.
    stored = AssistantPromptMessage.model_validate_json(
        AssistantPromptMessage(
            content="".join(chunk.delta.message.content or "" for chunk in chunks),
            tool_calls=[
                tool for chunk in chunks for tool in chunk.delta.message.tool_calls
            ],
            opaque_body=terminal.message.opaque_body,
        ).model_dump_json()
    )
    replay = llm._convert_prompt_message_to_dict(
        stored,
        {
            "_current_model": "deepseek-flash",
            "function_calling_type": "tool_call",
        },
    )
    assert replay["content"] == "Answer"
    assert replay["reasoning_content"] == reasoning
    assert replay["server_tool_calls"] == steps
    assert replay["tool_calls"] == function_calls
    assert "annotations" not in replay
    assert "title" not in replay
    assert "server_tool_use" not in replay


def test_server_tool_steps_are_not_merged_or_dropped():
    messages = [
        AssistantPromptMessage(
            content="", opaque_body={"server_tool_calls": [{"index": 0}]}
        ),
        AssistantPromptMessage(
            content="<think>\n<!--dify-deepseek-reasoning-->r\n</think>Answer"
        ),
        AssistantPromptMessage(
            content="Next", opaque_body={"server_tool_calls": [{"index": 0}]}
        ),
    ]
    assert _llm()._clean_messages(messages) == messages


@pytest.mark.parametrize(
    "model", ["deepseek-flash", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp"]
)
@pytest.mark.parametrize("enabled", [False, True])
def test_web_tools_without_client_functions(model, enabled):
    llm = _llm(model)
    with patch("requests.post", return_value=Mock(status_code=200)) as post:
        # _invoke is lazy for streams; inspect the request without consuming SSE.
        llm._invoke(
            model,
            {"api_key": "test"},
            [UserPromptMessage(content="Hi")],
            {
                "deepseek_web_search": enabled,
                "deepseek_read_url": enabled,
            },
        )
    request = json.loads(post.call_args.kwargs["data"])
    if enabled:
        assert request["tools"] == [
            {"type": "deepseek_web_search"},
            {"type": "deepseek_read_url"},
        ]
    else:
        assert "tools" not in request
    assert "deepseek_web_search" not in request
    assert "deepseek_read_url" not in request


@pytest.mark.parametrize("tool", ["deepseek_web_search", "deepseek_read_url"])
def test_web_tools_reject_json_output_before_sending(tool):
    with (
        patch("requests.post") as post,
        pytest.raises(ValueError, match="require the text response format"),
    ):
        _llm()._invoke(
            "deepseek-flash", {}, [], {tool: True, "response_format": "json_object"}
        )
    post.assert_not_called()


def test_stream_api_errors_keep_sdk_error_handling():
    response = Mock()
    response.iter_lines.return_value = ['data: {"error":{"message":"unavailable"}}']
    with pytest.raises(ValueError, match="unavailable"):
        list(
            _llm()._handle_generate_stream_response(
                "deepseek-flash",
                {"mode": "chat"},
                response,
                [UserPromptMessage(content="Hi")],
            )
        )


@pytest.mark.parametrize(
    "thinking", [None, False, True, {"type": "disabled"}, {"type": "enabled"}]
)
def test_reasoning_effort_none_and_thinking_precedence(thinking):
    parameters = {"reasoning_effort": "none", "temperature": 0.7, "thinking": thinking}
    _llm()._normalize_model_parameters("deepseek-flash", parameters)
    enabled = thinking is True or thinking == {"type": "enabled"}
    assert parameters["thinking"] == {"type": "enabled" if enabled else "disabled"}
    assert ("temperature" in parameters) is not enabled
    assert ("reasoning_effort" in parameters) is enabled


@pytest.mark.parametrize("stream", [False, True])
def test_title_and_refusal_without_reasoning_are_preserved(stream):
    response = Mock()
    metadata = {"title": "Title", "refusal": "Image rejected"}
    usage = {"prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 1}
    response.json.return_value = {
        "choices": [{"message": {"content": "", **metadata}}],
        "usage": usage,
    }
    response.iter_lines.return_value = [
        "data: "
        + json.dumps(
            {
                "choices": [{"delta": metadata, "finish_reason": "content_filter"}],
                "usage": usage,
            }
        ),
        "data: [DONE]",
    ]
    llm = _llm()
    args = (
        "deepseek-flash",
        {"mode": "chat"},
        response,
        [UserPromptMessage(content="hi")],
    )
    if stream:
        message = list(llm._handle_generate_stream_response(*args))[-1].delta.message
    else:
        message = llm._handle_generate_response(*args).message
    assert message.opaque_body == metadata
