from unittest.mock import Mock, patch

import pytest

from dify_plugin.errors.model import InvokeError
from dify_plugin.entities.model.llm import LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    SystemPromptMessage,
    UserPromptMessage,
)

from models.llm.llm import OpenAILargeLanguageModel


def _chat_response(message: dict) -> Mock:
    response = Mock()
    response.json.return_value = {
        "id": "chatcmpl-test",
        "model": "Qwen3.5-27B",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": message,
            }
        ],
        "usage": {
            "prompt_tokens": 11,
            "completion_tokens": 31,
            "total_tokens": 42,
        },
    }
    return response


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


@pytest.mark.parametrize(
    ("reasoning_key", "reasoning_value"),
    [
        ("reasoning", "vLLM reasoning trace"),
        ("reasoning_content", "legacy reasoning trace"),
    ],
)
def test_handle_generate_response_wraps_non_stream_reasoning_fields(
    reasoning_key: str, reasoning_value: str
):
    model = OpenAILargeLanguageModel(model_schemas=[])

    result = model._handle_generate_response(
        model="Qwen3.5-27B",
        credentials={"mode": "chat"},
        response=_chat_response(
            {
                "role": "assistant",
                "content": "final answer",
                reasoning_key: reasoning_value,
            }
        ),
        prompt_messages=[UserPromptMessage(content="test")],
    )

    assert result.message.content == f"<think>\n{reasoning_value}\n</think>final answer"
    assert result.usage.prompt_tokens == 11
    assert result.usage.completion_tokens == 31


def test_handle_generate_response_keeps_existing_think_content_when_reasoning_field_is_present():
    model = OpenAILargeLanguageModel(model_schemas=[])

    result = model._handle_generate_response(
        model="Qwen3.5-27B",
        credentials={"mode": "chat"},
        response=_chat_response(
            {
                "role": "assistant",
                "content": "<think>\ninline reasoning\n</think>\nfinal answer",
                "reasoning": "separate reasoning",
            }
        ),
        prompt_messages=[UserPromptMessage(content="test")],
    )

    assert result.message.content == "<think>\ninline reasoning\n</think>\nfinal answer"


def test_handle_generate_response_preserves_tool_calls_with_non_stream_reasoning():
    model = OpenAILargeLanguageModel(model_schemas=[])

    result = model._handle_generate_response(
        model="Qwen3.5-27B",
        credentials={"mode": "chat", "function_calling_type": "tool_call"},
        response=_chat_response(
            {
                "role": "assistant",
                "content": None,
                "reasoning": "need to call a tool",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "search_docs",
                            "arguments": "{\"query\":\"Qwen reasoning\"}",
                        },
                    }
                ],
            }
        ),
        prompt_messages=[UserPromptMessage(content="test")],
    )

    assert result.message.content == "<think>\nneed to call a tool\n</think>"
    assert result.message.tool_calls
    assert result.message.tool_calls[0].function.name == "search_docs"
    assert result.message.tool_calls[0].function.arguments == "{\"query\":\"Qwen reasoning\"}"


def _invoke_non_stream(
    model: OpenAILargeLanguageModel,
    credentials: dict,
    content: str,
    model_parameters: dict | None = None,
):
    def fake_super(self, model_name, credentials, prompt_messages, *args):
        return self._handle_generate_response(
            model=model_name,
            credentials=credentials,
            response=_chat_response({"role": "assistant", "content": content}),
            prompt_messages=prompt_messages,
        )

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ):
        return model._invoke(
            model="Qwen3.5-27B",
            credentials=credentials,
            prompt_messages=[UserPromptMessage(content="hello")],
            model_parameters=model_parameters or {},
            stream=False,
        )


def test_invoke_restores_prefilled_think_tag_and_filters_reasoning():
    model = OpenAILargeLanguageModel(model_schemas=[])

    # Qwen3.5's Jinja template prefills "<|im_start|>assistant\n<think>\n".
    # The API returns only the generated continuation, without the prompt prefix.
    result = _invoke_non_stream(
        model,
        {"mode": "chat", "agent_thought_support": "supported"},
        "reasoning</think>\n{\"class\":\"x\"}",
    )

    assert result.message.content == "<think>\nreasoning</think>\n{\"class\":\"x\"}"

    filtered_result = model._filter_thinking_result(result)

    assert filtered_result.message.content == "{\"class\":\"x\"}"


def test_invoke_strips_prefilled_reasoning_when_thinking_disabled():
    model = OpenAILargeLanguageModel(model_schemas=[])

    # Strict mode never sends the thinking switch, so Qwen3.5 still prefills `<think>`.
    result = _invoke_non_stream(
        model,
        {"mode": "chat"},
        "Format: {\"class\": \"...\"}</think>\n{\"class\":\"x\"}",
    )

    assert result.message.content == "{\"class\":\"x\"}"


@pytest.mark.parametrize(
    ("credentials", "model_parameters"),
    [
        ({"mode": "chat"}, {}),
        ({"mode": "chat", "agent_thought_support": "supported"}, {}),
        ({"mode": "chat", "agent_thought_support": "supported"}, {"enable_thinking": False}),
    ],
)
def test_invoke_preserves_literal_closing_think_tag_in_json_answer(credentials, model_parameters):
    model = OpenAILargeLanguageModel(model_schemas=[])

    result = _invoke_non_stream(model, credentials, "{\"tag\":\"</think>\"}", model_parameters)

    assert result.message.content == "{\"tag\":\"</think>\"}"


def _invoke_stream(credentials: dict, model_parameters: dict, pieces: list[str]) -> str:
    model = OpenAILargeLanguageModel(model_schemas=[])

    def fake_super(self, model_name, credentials, prompt_messages, *args):
        for index, piece in enumerate(pieces):
            yield LLMResultChunk(
                model=model_name,
                delta=LLMResultChunkDelta(
                    index=index, message=AssistantPromptMessage(content=piece)
                ),
            )

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ):
        chunks = model._invoke(
            model="Qwen3.5-27B",
            credentials={"mode": "chat", **credentials},
            prompt_messages=[UserPromptMessage(content="hello")],
            model_parameters=model_parameters,
            stream=True,
        )
        return "".join(chunk.delta.message.content for chunk in chunks)


@pytest.mark.parametrize(
    ("credentials", "model_parameters"),
    [
        ({"agent_thought_support": "supported"}, {"enable_thinking": True}),
        ({"agent_thought_support": "only_thinking_supported"}, {}),
    ],
)
def test_invoke_stream_restores_prefilled_think_tag(credentials, model_parameters):
    content = _invoke_stream(
        credentials, model_parameters, ["", "reason", "ing</th", "ink>\n{\"class\":\"x\"}"]
    )

    assert content == "<think>\nreasoning</think>\n{\"class\":\"x\"}"


@pytest.mark.parametrize(
    ("credentials", "model_parameters", "pieces"),
    [
        # Opening tag already present, split across chunks.
        ({"agent_thought_support": "supported"}, {"enable_thinking": True}, ["<th", "ink>r</think>x"]),
        # Thinking left to the model default: a hybrid model may answer without reasoning.
        ({"agent_thought_support": "supported"}, {}, ["{\"class\":", "\"x\"}"]),
    ],
)
def test_invoke_stream_keeps_content_without_prefilled_think_tag(
    credentials, model_parameters, pieces
):
    assert _invoke_stream(credentials, model_parameters, pieces) == "".join(pieces)


def test_filter_thinking_result_removes_wrapped_non_stream_reasoning():
    model = OpenAILargeLanguageModel(model_schemas=[])

    result = model._handle_generate_response(
        model="Qwen3.5-27B",
        credentials={"mode": "chat"},
        response=_chat_response(
            {
                "role": "assistant",
                "content": "final answer",
                "reasoning": "hidden reasoning",
            }
        ),
        prompt_messages=[UserPromptMessage(content="test")],
    )

    filtered_result = model._filter_thinking_result(result)

    assert filtered_result.message.content == "final answer"


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
