import sys
from pathlib import Path
from unittest.mock import Mock

import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
    VideoPromptMessageContent,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.llm.llm import MoonshotLargeLanguageModel  # noqa: E402


def _llm(schemas=None):
    return MoonshotLargeLanguageModel(model_schemas=schemas or [])


def test_non_stream_reasoning_round_trips_exactly():
    reasoning_content = "  must survive exactly\n"
    response = Mock()
    response.json.return_value = {
        "id": "chatcmpl-1",
        "model": "kimi-k3",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": reasoning_content,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "search", "arguments": "{}"},
                        }
                    ],
                },
            }
        ],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 2,
            "total_tokens": 3,
        },
    }
    credentials = {
        "mode": "chat",
        "function_calling_type": "tool_call",
    }
    llm = _llm()

    result = llm._handle_generate_response(
        "kimi-k3",
        credentials,
        response,
        [UserPromptMessage(content="hi")],
    )
    stored_message = AssistantPromptMessage(
        content=result.message.content,
        tool_calls=result.message.tool_calls,
    )

    for message in (result.message, stored_message):
        payload = llm._convert_prompt_message_to_dict(
            message,
            {
                "_current_model": "kimi-k3",
                "function_calling_type": "tool_call",
            },
        )
        assert payload["content"] == ""
        assert payload["reasoning_content"] == reasoning_content
        assert payload["tool_calls"][0]["id"] == "call_1"


def test_video_content_is_serialized_in_order():
    llm = _llm()
    [message] = llm._clean_messages(
        [
            UserPromptMessage(content="Watch "),
            UserPromptMessage(
                content=[
                    VideoPromptMessageContent(
                        format="base64",
                        base64_data="AAAA",
                        mime_type="video/mp4",
                    ),
                ],
            ),
            UserPromptMessage(
                content=[TextPromptMessageContent(data=" carefully.")],
            ),
        ],
    )

    assert llm._convert_prompt_message_to_dict(message) == {
        "role": "user",
        "content": [
            {"type": "text", "text": "Watch "},
            {
                "type": "video_url",
                "video_url": {"url": "data:video/mp4;base64,AAAA"},
            },
            {"type": "text", "text": " carefully."},
        ],
    }


def test_thinking_model_detection_is_exact():
    message = AssistantPromptMessage(content="answer")
    llm = _llm()

    for model in (
        "kimi-k2.5",
        "kimi-k2.6",
        "kimi-k2.7-code",
        "kimi-k2.7-code-highspeed",
        "kimi-k3",
        "kimi-k2-thinking",
        "kimi-k2-thinking-turbo",
    ):
        payload = llm._convert_prompt_message_to_dict(
            message,
            {"_current_model": model},
        )
        assert payload["reasoning_content"] == ""

    for model in (
        "grok3-custom",
        "acme-k3-instant",
        "kimi-k30",
        "my-k2.7-proxy",
    ):
        payload = llm._convert_prompt_message_to_dict(
            message,
            {"_current_model": model},
        )
        assert "reasoning_content" not in payload


def test_adjacent_assistant_reasoning_is_not_lost():
    llm = _llm()
    [message] = llm._clean_messages(
        [
            AssistantPromptMessage(
                content="<think>r1</think>a",
                opaque_body={"reasoning_content": "r1"},
            ),
            AssistantPromptMessage(
                content="<think>r2</think>b",
                opaque_body={"reasoning_content": "r2"},
            ),
        ],
    )

    assert llm._convert_prompt_message_to_dict(
        message,
        {"_current_model": "kimi-k3"},
    ) == {
        "role": "assistant",
        "content": "a\n\nb",
        "reasoning_content": "r1\n\nr2",
    }


def test_stream_reasoning_ignores_empty_chunks():
    llm = _llm()

    opening, is_reasoning = llm._wrap_thinking_by_reasoning_content(
        {"reasoning_content": ""},
        False,
    )
    assert opening == ""
    assert is_reasoning is False

    reasoning, is_reasoning = llm._wrap_thinking_by_reasoning_content(
        {"reasoning_content": "reason"},
        is_reasoning,
    )
    empty, is_reasoning = llm._wrap_thinking_by_reasoning_content(
        {"reasoning_content": "", "tool_calls": [{}]},
        is_reasoning,
    )
    answer, is_reasoning = llm._wrap_thinking_by_reasoning_content(
        {"content": "answer"},
        is_reasoning,
    )

    assert opening + reasoning + empty + answer == "<think>reason</think>answer"
    assert is_reasoning is False
    assert llm._wrap_thinking_by_reasoning_content(
        {"reasoning_content": "", "content": "answer"},
        False,
    ) == ("answer", False)


def test_legacy_max_tokens_maps_to_max_completion_tokens():
    for model in (
        "kimi-k3",
        "kimi-k2.7-code",
        "kimi-k2.7-code-highspeed",
    ):
        raw = yaml.safe_load(
            (ROOT / "models" / "llm" / f"{model}.yaml").read_text(),
        )
        llm = _llm([AIModelEntity.model_validate(raw)])

        assert llm._validate_and_filter_model_parameters(
            model,
            {"max_tokens": 123},
            {},
        ) == {"max_completion_tokens": 123}
