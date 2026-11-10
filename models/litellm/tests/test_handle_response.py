from unittest.mock import Mock

import pytest
from dify_plugin.entities.model.message import UserPromptMessage
from dify_plugin.errors.model import InvokeError

from models.llm.llm import LiteLLMLargeLanguageModel

TOOL_CALL = {
    "id": "call_123",
    "type": "function",
    "function": {"name": "search_docs", "arguments": '{"query":"LiteLLM"}'},
}


def _response(choice: dict, usage: dict | None = None) -> Mock:
    payload = {"id": "chatcmpl-test", "model": "gpt-6-luna", "choices": [choice]}
    if usage is not None:
        payload["usage"] = usage
    response = Mock()
    response.json.return_value = payload
    return response


def _handle(response: Mock, **credentials):
    model = LiteLLMLargeLanguageModel(model_schemas=[])
    return model._handle_generate_response(
        model="gpt-6-luna",
        credentials={"mode": "chat", **credentials},
        response=response,
        prompt_messages=[UserPromptMessage(content="hello")],
    )


USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


def test_message_with_content() -> None:
    result = _handle(_response({"message": {"role": "assistant", "content": "Hi there"}}, USAGE))

    assert result.message.content == "Hi there"
    assert result.message.tool_calls == []
    assert result.model == "gpt-6-luna"
    assert result.usage.prompt_tokens == 10
    assert result.usage.completion_tokens == 5


def test_tool_calls_without_content_key() -> None:
    response = _response({"message": {"role": "assistant", "tool_calls": [TOOL_CALL]}}, USAGE)

    result = _handle(response, function_calling_type="tool_call")

    assert result.message.content == ""
    assert len(result.message.tool_calls) == 1
    assert result.message.tool_calls[0].id == "call_123"
    assert result.message.tool_calls[0].function.name == "search_docs"
    assert result.message.tool_calls[0].function.arguments == '{"query":"LiteLLM"}'


def test_tool_calls_with_null_content() -> None:
    response = _response(
        {"message": {"role": "assistant", "content": None, "tool_calls": [TOOL_CALL]}}, USAGE
    )

    result = _handle(response, function_calling_type="tool_call")

    assert result.message.content == ""
    assert result.message.tool_calls[0].function.name == "search_docs"


def test_function_call_without_content_key() -> None:
    function_call = {"name": "search_docs", "arguments": '{"query":"LiteLLM"}'}
    response = _response({"message": {"role": "assistant", "function_call": function_call}}, USAGE)

    result = _handle(response, function_calling_type="function_call")

    assert result.message.content == ""
    assert len(result.message.tool_calls) == 1
    assert result.message.tool_calls[0].function.name == "search_docs"


def test_tool_calls_are_ignored_when_function_calling_is_off() -> None:
    response = _response({"message": {"role": "assistant", "tool_calls": [TOOL_CALL]}}, USAGE)

    result = _handle(response, function_calling_type="no_call")

    assert result.message.tool_calls == []


def test_missing_message_gives_empty_content() -> None:
    result = _handle(_response({"finish_reason": "stop"}, USAGE))

    assert result.message.content == ""


def test_completion_mode_reads_text() -> None:
    result = _handle(_response({"text": "done"}, USAGE), mode="completion")

    assert result.message.content == "done"


def test_usage_is_estimated_when_the_proxy_leaves_it_out() -> None:
    result = _handle(_response({"message": {"role": "assistant", "content": "Hi there"}}))

    assert result.usage.prompt_tokens > 0
    assert result.usage.completion_tokens > 0


@pytest.mark.parametrize("choices", [[], None])
def test_empty_choices_raise_invoke_error(choices) -> None:
    response = Mock()
    response.json.return_value = {"id": "chatcmpl-test", "choices": choices}

    with pytest.raises(InvokeError, match="without choices"):
        _handle(response)
