import sys
from pathlib import Path
from types import SimpleNamespace

import yaml
from dify_plugin.entities.model.message import (
    ImagePromptMessageContent,
    TextPromptMessageContent,
    UserPromptMessage,
    VideoPromptMessageContent,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.llm.llm import MinimaxLargeLanguageModel  # noqa: E402


def _llm() -> MinimaxLargeLanguageModel:
    return MinimaxLargeLanguageModel(model_schemas=[])


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
    assert rules["thinking"]["options"] == ["adaptive", "disabled"]


def test_m3_thinking_uses_adaptive_or_disabled() -> None:
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
    ) == {"type": "disabled"}
    assert llm._normalize_thinking_payload(
        thinking=True,
        thinking_budget=1024,
        request_model="MiniMax-M3",
    ) == {"type": "adaptive"}


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
