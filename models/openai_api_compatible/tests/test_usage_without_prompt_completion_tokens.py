"""Gateways that report usage with non-standard keys must not fail the call.

Most OpenAI-compatible endpoints report prompt_tokens/completion_tokens, but
Anthropic-compatible proxies report input_tokens/output_tokens, and some
deployments report only total_tokens. Indexing the OpenAI names raised
KeyError on a response whose content was perfectly usable.
"""

from unittest.mock import Mock

import pytest

from dify_plugin.entities.model.message import UserPromptMessage
from dify_plugin.errors.model import InvokeError

from models.llm.llm import OpenAILargeLanguageModel


def _chat_response(message: dict, usage: dict) -> Mock:
    response = Mock()
    response.json.return_value = {
        "id": "chatcmpl-test",
        "model": "some-model",
        "choices": [
            {"index": 0, "finish_reason": "stop", "message": message},
        ],
        "usage": usage,
    }
    return response


def _credentials() -> dict:
    return {"mode": "chat", "function_calling_type": "no_call"}


def test_input_output_token_names_are_accepted():
    """An Anthropic-compatible proxy reports input_tokens/output_tokens."""
    model = OpenAILargeLanguageModel(model_schemas=[])

    result = model._handle_generate_response(
        model="some-model",
        credentials=_credentials(),
        response=_chat_response(
            {"role": "assistant", "content": "hello"},
            {"input_tokens": 11, "output_tokens": 5},
        ),
        prompt_messages=[UserPromptMessage(content="test")],
    )

    assert result.message.content == "hello"
    assert result.usage.prompt_tokens == 11
    assert result.usage.completion_tokens == 5


def test_partial_token_report_falls_back_instead_of_raising():
    """A gateway reporting only one direction must not raise KeyError."""
    model = OpenAILargeLanguageModel(model_schemas=[])

    result = model._handle_generate_response(
        model="some-model",
        credentials=_credentials(),
        response=_chat_response(
            {"role": "assistant", "content": "hello"},
            {"prompt_tokens": 11},
        ),
        prompt_messages=[UserPromptMessage(content="test")],
    )

    assert result.message.content == "hello"
    assert result.usage.prompt_tokens == 11
    assert result.usage.completion_tokens >= 0


def test_total_only_usage_falls_back_instead_of_raising():
    """A gateway reporting only total_tokens must not raise KeyError."""
    model = OpenAILargeLanguageModel(model_schemas=[])

    result = model._handle_generate_response(
        model="some-model",
        credentials=_credentials(),
        response=_chat_response(
            {"role": "assistant", "content": "hello"},
            {"total_tokens": 42},
        ),
        prompt_messages=[UserPromptMessage(content="test")],
    )

    assert result.message.content == "hello"
    assert result.usage.prompt_tokens >= 0
    assert result.usage.completion_tokens >= 0


def test_empty_choices_still_raise():
    """The existing empty-choices guard is unchanged."""
    model = OpenAILargeLanguageModel(model_schemas=[])
    response = Mock()
    response.json.return_value = {"choices": [], "usage": {}}

    with pytest.raises(InvokeError, match="no choices"):
        model._handle_generate_response(
            model="some-model",
            credentials=_credentials(),
            response=response,
            prompt_messages=[UserPromptMessage(content="test")],
        )
