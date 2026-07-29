import sys
from pathlib import Path
from types import SimpleNamespace

import yaml
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    TextPromptMessageContent,
    UserPromptMessage,
    VideoPromptMessageContent,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.llm.llm import MinimaxLargeLanguageModel  # noqa: E402


def _llm() -> MinimaxLargeLanguageModel:
    return MinimaxLargeLanguageModel(model_schemas=[])


def _event(event_type: str, **kwargs) -> SimpleNamespace:
    return SimpleNamespace(type=event_type, **kwargs)


def _usage(input_tokens: int = 1, output_tokens: int = 1) -> SimpleNamespace:
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)


def test_m3_model_alias() -> None:
    assert _llm()._resolve_model_name("minimax-m3") == "MiniMax-M3"


def test_m3_yaml_parameters_match_official_limits() -> None:
    model_file = Path(__file__).parent.parent / "models" / "llm" / "minimax-m3.yaml"
    model_schema = yaml.safe_load(model_file.read_text(encoding="utf-8"))
    rules = {rule["name"]: rule for rule in model_schema["parameter_rules"]}

    assert model_schema["model"] == "minimax-m3"
    assert model_schema["model_properties"]["context_size"] == 1000000
    assert model_schema["features"] == [
        "agent-thought",
        "vision",
        "video",
        "tool-call",
        "stream-tool-call",
    ]
    assert rules["temperature"]["min"] == 0
    assert rules["temperature"]["max"] == 2
    assert rules["temperature"]["default"] == 1
    assert rules["top_p"]["min"] == 0
    assert rules["top_p"]["max"] == 1
    assert rules["top_p"]["default"] == 0.95
    assert rules["max_tokens"]["max"] == 524288
    assert rules["thinking"]["options"] == ["adaptive"]


def test_m3_thinking_uses_adaptive_or_omits_unsupported_modes() -> None:
    llm = _llm()

    assert llm._normalize_thinking_payload(
        thinking="adaptive",
        thinking_budget=1024,
        request_model="MiniMax-M3",
    ) == {"type": "adaptive"}
    assert llm._normalize_thinking_payload(
        thinking=False,
        thinking_budget=1024,
        request_model="MiniMax-M3",
    ) is None
    assert llm._normalize_thinking_payload(
        thinking=True,
        thinking_budget=1024,
        request_model="MiniMax-M3",
    ) == {"type": "adaptive"}
    assert llm._normalize_thinking_payload(
        thinking="enabled",
        thinking_budget=1024,
        request_model="MiniMax-M3",
    ) == {"type": "adaptive"}
    assert llm._normalize_thinking_payload(
        thinking="false",
        thinking_budget=1024,
        request_model="MiniMax-M3",
    ) is None
    assert llm._normalize_thinking_payload(
        thinking="disabled",
        thinking_budget=1024,
        request_model="MiniMax-M3",
    ) is None


def test_m2_thinking_keeps_budget_payload() -> None:
    assert _llm()._normalize_thinking_payload(
        thinking=True,
        thinking_budget=2048,
        request_model="MiniMax-M2.7",
    ) == {"type": "enabled", "budget_tokens": 2048}


def test_m3_multimodal_user_message_uses_anthropic_sources() -> None:
    message = UserPromptMessage(
        content=[
            TextPromptMessageContent(data="Describe these inputs."),
            ImagePromptMessageContent(
                format="url",
                url="https://example.com/image.png",
                mime_type="image/png",
            ),
            VideoPromptMessageContent(
                format="base64",
                base64_data="AAAA",
                mime_type="video/mp4",
            ),
        ]
    )

    converted = _llm()._convert_prompt_message_to_anthropic_message(message)

    assert converted == {
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe these inputs."},
            {
                "type": "image",
                "source": {
                    "type": "url",
                    "url": "https://example.com/image.png",
                },
            },
            {
                "type": "video",
                "source": {
                    "type": "base64",
                    "media_type": "video/mp4",
                    "data": "AAAA",
                },
            },
        ],
    }


def test_dict_media_payload_accepts_url_string_values() -> None:
    converted = _llm()._convert_user_content_blocks(
        [
            {"type": "image", "image_url": "https://example.com/image.png"},
            {"type": "video_url", "video_url": "https://example.com/video.mp4"},
        ]
    )

    assert converted == [
        {
            "type": "image",
            "source": {
                "type": "url",
                "url": "https://example.com/image.png",
            },
        },
        {
            "type": "video",
            "source": {
                "type": "url",
                "url": "https://example.com/video.mp4",
            },
        },
    ]


def test_dict_media_payload_accepts_nested_url_values() -> None:
    converted = _llm()._convert_user_content_blocks(
        [
            {"type": "image_url", "image_url": {"url": "https://example.com/image.png"}},
            {"type": "video", "video_url": {"url": "https://example.com/video.mp4"}},
        ]
    )

    assert converted == [
        {
            "type": "image",
            "source": {
                "type": "url",
                "url": "https://example.com/image.png",
            },
        },
        {
            "type": "video",
            "source": {
                "type": "url",
                "url": "https://example.com/video.mp4",
            },
        },
    ]


def test_object_content_type_accepts_string_values() -> None:
    converted = _llm()._convert_user_content_blocks(
        [
            SimpleNamespace(type="text", data="What is shown?"),
            SimpleNamespace(type="image", data="https://example.com/image.png"),
            SimpleNamespace(type="video", data="https://example.com/video.mp4"),
        ]
    )

    assert converted == [
        {"type": "text", "text": "What is shown?"},
        {
            "type": "image",
            "source": {
                "type": "url",
                "url": "https://example.com/image.png",
            },
        },
        {
            "type": "video",
            "source": {
                "type": "url",
                "url": "https://example.com/video.mp4",
            },
        },
    ]


def test_stream_tool_call_arguments_use_delta_buffer() -> None:
    llm = _llm()
    events = [
        _event("message_start", message=SimpleNamespace(usage=_usage())),
        _event(
            "content_block_start",
            index=0,
            content_block=SimpleNamespace(type="tool_use", id="call_1", name="search", input={}),
        ),
        _event(
            "content_block_delta",
            index=0,
            delta=SimpleNamespace(type="input_json_delta", partial_json='{"query":'),
        ),
        _event(
            "content_block_delta",
            index=0,
            delta=SimpleNamespace(type="input_json_delta", partial_json='"m3"}'),
        ),
        _event(
            "message_delta",
            delta=SimpleNamespace(stop_reason="tool_use"),
            usage=_usage(output_tokens=2),
        ),
        _event("message_stop"),
    ]

    chunks = list(
        llm._handle_chat_generate_stream_response(
            model="minimax-m3",
            prompt_messages=[UserPromptMessage(content="hi")],
            credentials={},
            response=events,
        )
    )

    final_message = chunks[-1].delta.message
    assert final_message.tool_calls[0].function.arguments == '{"query":"m3"}'
    assert final_message.opaque_body == {
        "minimax_anthropic_content": [
            {
                "type": "tool_use",
                "id": "call_1",
                "name": "search",
                "input": {"query": "m3"},
            }
        ]
    }


def test_stream_tool_call_keeps_input_fallback_without_delta() -> None:
    llm = _llm()
    events = [
        _event("message_start", message=SimpleNamespace(usage=_usage())),
        _event(
            "content_block_start",
            index=0,
            content_block=SimpleNamespace(
                type="tool_use",
                id="call_1",
                name="read",
                input={"path": "a.txt"},
            ),
        ),
        _event(
            "message_delta",
            delta=SimpleNamespace(stop_reason="tool_use"),
            usage=_usage(output_tokens=2),
        ),
        _event("message_stop"),
    ]

    chunks = list(
        llm._handle_chat_generate_stream_response(
            model="minimax-m3",
            prompt_messages=[UserPromptMessage(content="hi")],
            credentials={},
            response=events,
        )
    )

    assert chunks[-1].delta.message.tool_calls[0].function.arguments == '{"path": "a.txt"}'


def test_stream_thinking_closes_before_tool_call_without_text_delta() -> None:
    llm = _llm()
    events = [
        _event("message_start", message=SimpleNamespace(usage=_usage())),
        _event(
            "content_block_start",
            index=0,
            content_block=SimpleNamespace(type="thinking", signature="sig"),
        ),
        _event(
            "content_block_delta",
            index=0,
            delta=SimpleNamespace(type="thinking_delta", thinking="reason"),
        ),
        _event(
            "content_block_start",
            index=1,
            content_block=SimpleNamespace(type="tool_use", id="call_1", name="search", input={}),
        ),
        _event(
            "message_delta",
            delta=SimpleNamespace(stop_reason="tool_use"),
            usage=_usage(output_tokens=2),
        ),
        _event("message_stop"),
    ]

    chunks = list(
        llm._handle_chat_generate_stream_response(
            model="minimax-m3",
            prompt_messages=[UserPromptMessage(content="hi")],
            credentials={},
            response=events,
        )
    )

    contents = [chunk.delta.message.content for chunk in chunks]
    assert contents[:3] == ["<think>\n", "reason", "\n</think>\n"]
    assert contents.count("\n</think>\n") == 1
    assert chunks[-1].delta.message.opaque_body == {
        "minimax_anthropic_content": [
            {"type": "thinking", "thinking": "reason", "signature": "sig"},
            {"type": "tool_use", "id": "call_1", "name": "search", "input": {}},
        ]
    }


def test_non_stream_tool_call_replays_opaque_content_without_duplicate_thinking_text() -> None:
    llm = _llm()
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="reason", signature="sig"),
            SimpleNamespace(type="text", text="I will call a tool."),
            SimpleNamespace(type="tool_use", id="call_1", name="search", input={"query": "m3"}),
        ],
        usage=_usage(output_tokens=2),
    )

    result = llm._handle_chat_generate_response(
        model="minimax-m3",
        prompt_messages=[UserPromptMessage(content="hi")],
        credentials={},
        response=response,
    )
    converted = llm._convert_prompt_message_to_anthropic_message(result.message)

    assert result.message.content == "<think>reason</think>\nI will call a tool."
    assert converted == {
        "role": "assistant",
        "content": [
            {"type": "thinking", "thinking": "reason", "signature": "sig"},
            {"type": "text", "text": "I will call a tool."},
            {"type": "tool_use", "id": "call_1", "name": "search", "input": {"query": "m3"}},
        ],
    }


def test_previous_thinking_fallback_strips_tagged_text_on_tool_replay() -> None:
    llm = _llm()
    llm._set_previous_thinking_blocks(
        [{"type": "thinking", "thinking": "reason", "signature": "sig"}]
    )
    message = AssistantPromptMessage(
        content="<think>reason</think>\nI will call a tool.",
        tool_calls=[
            AssistantPromptMessage.ToolCall(
                id="call_1",
                type="function",
                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                    name="search",
                    arguments='{"query": "m3"}',
                ),
            )
        ],
    )

    converted = llm._convert_prompt_message_to_anthropic_message(message)

    assert converted == {
        "role": "assistant",
        "content": [
            {"type": "thinking", "thinking": "reason", "signature": "sig"},
            {"type": "text", "text": "I will call a tool."},
            {"type": "tool_use", "id": "call_1", "name": "search", "input": {"query": "m3"}},
        ],
    }
