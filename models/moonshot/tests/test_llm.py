import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import (
    AIModelEntity,
    ModelFeature,
    ModelPropertyKey,
)
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
    VideoPromptMessageContent,
)
from dify_plugin.errors.model import CredentialsValidateFailedError

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


@pytest.mark.parametrize(
    ("model", "context_size", "default_tokens", "max_tokens"),
    [
        ("kimi-k3", 1_048_576, 131_072, 1_048_576),
        ("kimi-k2.7-code", 262_144, 32_768, 262_144),
        ("kimi-k2.7-code-highspeed", 262_144, 32_768, 262_144),
    ],
)
def test_new_model_schema_and_token_limits(
    model: str,
    context_size: int,
    default_tokens: int,
    max_tokens: int,
):
    raw = yaml.safe_load(
        (ROOT / "models" / "llm" / f"{model}.yaml").read_text(),
    )
    schema = AIModelEntity.model_validate(raw)
    rules = {rule.name: rule for rule in schema.parameter_rules}
    token_rule = rules["max_completion_tokens"]

    assert schema.model_properties[ModelPropertyKey.CONTEXT_SIZE] == context_size
    assert {
        ModelFeature.VIDEO,
        ModelFeature.STRUCTURED_OUTPUT,
    }.issubset(schema.features or [])
    assert token_rule.use_template == "max_tokens"
    assert token_rule.default == default_tokens
    assert token_rule.max == max_tokens
    assert "json_schema" in rules["response_format"].options
    assert rules["json_schema"].use_template == "json_schema"

    llm = _llm([schema])
    assert llm._validate_and_filter_model_parameters(
        model,
        {"max_tokens": max_tokens},
        {},
    ) == {"max_completion_tokens": max_tokens}
    with pytest.raises(ValueError, match="less than or equal"):
        llm._validate_and_filter_model_parameters(
            model,
            {"max_completion_tokens": max_tokens + 1},
            {},
        )


def test_json_schema_is_sent_to_api():
    model = "kimi-k2.7-code"
    raw = yaml.safe_load(
        (ROOT / "models" / "llm" / f"{model}.yaml").read_text(),
    )
    llm = _llm([AIModelEntity.model_validate(raw)])
    output_schema = {
        "name": "moonshot_test",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        },
    }
    response = Mock()
    response.status_code = 200
    response.encoding = "utf-8"
    response.json.return_value = {
        "id": "chatcmpl-1",
        "model": model,
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": '{"answer":"ok"}',
                },
            }
        ],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 2,
            "total_tokens": 3,
        },
    }

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.requests.post",
        return_value=response,
    ) as post:
        chunks = list(
            llm.invoke(
                model=model,
                credentials={"api_key": "test"},
                prompt_messages=[UserPromptMessage(content="Reply with JSON.")],
                model_parameters={
                    "max_tokens": 128,
                    "response_format": "json_schema",
                    "json_schema": json.dumps(output_schema),
                },
                stream=False,
            ),
        )

    request = post.call_args.kwargs["json"]
    assert request["max_completion_tokens"] == 128
    assert request["response_format"] == {
        "type": "json_schema",
        "json_schema": output_schema,
    }
    assert "json_schema" not in request
    assert chunks[0].delta.message.content == '{"answer":"ok"}'


INTERNATIONAL = "https://api.moonshot.ai/v1"
MAINLAND = "https://api.moonshot.cn/v1"


def _base_validate_accepting(valid_endpoint, attempts):
    """A fake OAICompat base validate_credentials that authenticates only for
    valid_endpoint and records every endpoint it was called with."""

    def _validate(self, model, credentials):
        attempts.append(credentials.get("endpoint_url"))
        if credentials.get("endpoint_url") != valid_endpoint:
            raise CredentialsValidateFailedError(
                f"401 invalid_authentication_error for {credentials.get('endpoint_url')}"
            )

    return _validate


def test_blank_endpoint_resolves_to_international_and_persists():
    llm = _llm()
    credentials = {"api_key": "intl-key"}
    attempts = []
    with patch.object(
        OAICompatLargeLanguageModel,
        "validate_credentials",
        _base_validate_accepting(INTERNATIONAL, attempts),
    ):
        llm.validate_credentials("moonshot-v1-8k", credentials)

    assert credentials["endpoint_url"] == INTERNATIONAL
    assert attempts[0] == INTERNATIONAL  # international tried first


def test_blank_endpoint_resolves_to_mainland_and_persists():
    llm = _llm()
    credentials = {"api_key": "cn-key"}
    attempts = []
    with patch.object(
        OAICompatLargeLanguageModel,
        "validate_credentials",
        _base_validate_accepting(MAINLAND, attempts),
    ):
        llm.validate_credentials("moonshot-v1-8k", credentials)

    assert credentials["endpoint_url"] == MAINLAND
    assert attempts == [INTERNATIONAL, MAINLAND]  # international first, then mainland


def test_blank_endpoint_invalid_key_surfaces_original_error_and_persists_nothing():
    llm = _llm()
    credentials = {"api_key": "bad-key"}
    attempts = []
    with patch.object(
        OAICompatLargeLanguageModel,
        "validate_credentials",
        _base_validate_accepting("neither", attempts),
    ):
        with pytest.raises(CredentialsValidateFailedError) as excinfo:
            llm.validate_credentials("moonshot-v1-8k", credentials)

    assert attempts == [INTERNATIONAL, MAINLAND]  # both tried
    assert MAINLAND in str(excinfo.value)  # original mainland 401 surfaced, not synthesized
    assert not credentials.get("endpoint_url")  # nothing persisted on failure


def test_explicit_endpoint_is_used_as_is_with_no_fallback():
    llm = _llm()
    proxy = "https://proxy.internal.example/v1"
    credentials = {"api_key": "k", "endpoint_url": proxy}
    attempts = []
    with patch.object(
        OAICompatLargeLanguageModel,
        "validate_credentials",
        _base_validate_accepting(proxy, attempts),
    ):
        llm.validate_credentials("moonshot-v1-8k", credentials)

    assert credentials["endpoint_url"] == proxy  # untouched
    assert attempts == [proxy]  # exactly one attempt, no fallback probing
