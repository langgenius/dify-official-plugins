from unittest.mock import Mock

from dify_plugin.entities.model.message import UserPromptMessage

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
