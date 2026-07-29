from unittest.mock import Mock, patch

from dify_plugin.errors.model import InvokeError
from dify_plugin.entities.model.message import SystemPromptMessage, UserPromptMessage

from models.llm.llm import OpenAILargeLanguageModel


def test_handle_generate_response_accepts_tool_calls_without_content_key():
    model = OpenAILargeLanguageModel(model_schemas=[])
    response = Mock()
    response.json.return_value = {
        "id": "chatcmpl-tool-only",
        "model": "gpt-5-mini",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "search_docs",
                                "arguments": "{\"query\":\"LiteLLM\"}",
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }

    result = model._handle_generate_response(
        model="gpt-5-mini",
        credentials={"mode": "chat", "function_calling_type": "tool_call"},
        response=response,
        prompt_messages=[UserPromptMessage(content="test")],
    )

    assert result.message.content == ""
    assert result.message.tool_calls
    assert result.message.tool_calls[0].function.name == "search_docs"
    assert result.message.tool_calls[0].function.arguments == "{\"query\":\"LiteLLM\"}"


def test_handle_generate_response_normalizes_null_content():
    model = OpenAILargeLanguageModel(model_schemas=[])
    response = Mock()
    response.json.return_value = {
        "id": "chatcmpl-null-content",
        "model": "gpt-5-mini",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_456",
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "arguments": "{\"id\":1}",
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {
            "prompt_tokens": 8,
            "completion_tokens": 4,
            "total_tokens": 12,
        },
    }

    result = model._handle_generate_response(
        model="gpt-5-mini",
        credentials={"mode": "chat", "function_calling_type": "tool_call"},
        response=response,
        prompt_messages=[UserPromptMessage(content="test")],
    )

    assert result.message.content == ""
    assert result.message.tool_calls
    assert result.message.tool_calls[0].function.name == "lookup"


def test_handle_generate_response_counts_all_prompt_messages_when_usage_missing():
    model = OpenAILargeLanguageModel(model_schemas=[])
    response = Mock()
    response.json.return_value = {
        "id": "chatcmpl-missing-usage",
        "model": "gpt-5-mini",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_789",
                            "type": "function",
                            "function": {
                                "name": "search_docs",
                                "arguments": "{\"query\":\"history\"}",
                            },
                        }
                    ],
                },
            }
        ],
    }
    prompt_messages = [
        SystemPromptMessage(content="system prompt"),
        UserPromptMessage(content="latest user message"),
    ]
    credentials = {"mode": "chat", "function_calling_type": "tool_call"}

    with (
        patch.object(model, "_num_tokens_from_messages", return_value=11) as mock_prompt_counter,
        patch.object(model, "_num_tokens_from_string", return_value=3) as mock_string_counter,
    ):
        result = model._handle_generate_response(
            model="gpt-5-mini",
            credentials=credentials,
            response=response,
            prompt_messages=prompt_messages,
        )

    mock_prompt_counter.assert_called_once_with(prompt_messages, credentials=credentials)
    mock_string_counter.assert_called_once_with("")
    assert result.usage.prompt_tokens == 11
    assert result.usage.completion_tokens == 3


def test_handle_generate_response_raises_when_choices_missing():
    model = OpenAILargeLanguageModel(model_schemas=[])
    response = Mock()
    response.json.return_value = {
        "id": "chatcmpl-empty-choices",
        "model": "gpt-5-mini",
        "choices": [],
    }

    try:
        model._handle_generate_response(
            model="gpt-5-mini",
            credentials={"mode": "chat", "function_calling_type": "tool_call"},
            response=response,
            prompt_messages=[UserPromptMessage(content="test")],
        )
    except InvokeError as exc:
        assert str(exc) == "LLM response returned no choices"
    else:
        raise AssertionError("Expected InvokeError for empty choices")
