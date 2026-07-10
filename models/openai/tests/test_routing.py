from __future__ import annotations

import hashlib

import pytest

from dify_plugin.entities.model.message import PromptMessageTool
from dify_plugin.errors.model import InvokeBadRequestError
from models.llm import chat, responses, stream as response_stream
from models.llm.llm import _base_model, _uses_responses


def test_reasoning_parameters_are_merged_without_mutating_the_caller() -> None:
    source = {
        "reasoning": {"effort": "low"},
        "reasoning_effort": "none",
        "reasoning_summary": "detailed",
        "reasoning_mode": "pro",
        "reasoning_context": "all_turns",
    }

    result = responses.parameters("gpt-5.6", source, None, None)

    assert result["reasoning"] == {
        "effort": "none",
        "summary": "detailed",
        "mode": "pro",
        "context": "all_turns",
    }
    assert source["reasoning"] == {"effort": "low"}


def test_structured_output_and_service_tier_are_mapped() -> None:
    schema = {
        "name": "answer",
        "description": "A structured answer",
        "schema": {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        },
        "strict": True,
    }

    result = responses.parameters(
        "gpt-5.6",
        {
            "max_completion_tokens": 512,
            "response_format": {"type": "json_schema", "json_schema": schema},
            "verbosity": "high",
            "service_tier": "priority",
        },
        None,
        None,
    )

    assert result["max_output_tokens"] == 512
    assert result["text"] == {
        "format": {"type": "json_schema", **schema},
        "verbosity": "high",
    }
    assert result["service_tier"] == "priority"
    assert (
        not {
            "max_completion_tokens",
            "response_format",
            "verbosity",
        }
        & result.keys()
    )


@pytest.mark.parametrize(
    ("parameters", "match"),
    [
        ({"presence_penalty": 0.1}, "presence_penalty"),
        ({"frequency_penalty": -0.1}, "frequency_penalty"),
        ({"seed": 0}, "seed"),
        ({"reasoning": []}, "reasoning must be an object"),
        ({"text": []}, "text must be an object"),
        ({"response_format": "json_schema", "json_schema": "{"}, "valid JSON"),
    ],
)
def test_unsupported_or_malformed_parameters_are_rejected(parameters, match) -> None:
    with pytest.raises(InvokeBadRequestError, match=match):
        responses.parameters("gpt-5.6", parameters, None, None)


def test_neutral_chat_penalties_are_removed() -> None:
    result = responses.parameters(
        "gpt-5.6",
        {"presence_penalty": 0.0, "frequency_penalty": 0, "seed": None},
        None,
        None,
    )
    assert not {"presence_penalty", "frequency_penalty", "seed"} & result.keys()


@pytest.mark.parametrize(
    ("source", "expected_include"),
    [
        ({}, ["reasoning.encrypted_content"]),
        (
            {"store": False, "include": ["web_search_call.action.sources"]},
            ["web_search_call.action.sources", "reasoning.encrypted_content"],
        ),
        (
            {"store": False, "include": ["reasoning.encrypted_content"]},
            ["reasoning.encrypted_content"],
        ),
        ({"store": True}, None),
    ],
)
def test_stateless_requests_include_encrypted_reasoning(
    source, expected_include
) -> None:
    source = {**source, "user": "parameter-user"}
    result = responses.parameters("gpt-5.6", source, None, "user-123")
    digest = hashlib.sha256(b"user-123").hexdigest()

    assert result["store"] is source.get("store", False)
    assert result.get("include") == expected_include
    assert result["safety_identifier"] == digest
    assert result["prompt_cache_key"] == digest
    assert "user" not in result


def test_tool_shape_and_named_choice_match_responses() -> None:
    tool = PromptMessageTool(
        name="lookup",
        description="Look up a value",
        parameters={"type": "object", "properties": {}},
    )

    result = responses.parameters(
        "gpt-5.6",
        {
            "tool_choice": {
                "type": "function",
                "function": {"name": "lookup"},
            }
        },
        [tool],
        None,
    )

    assert result["tool_choice"] == {"type": "function", "name": "lookup"}
    assert result["tools"] == [
        {
            "type": "function",
            "name": "lookup",
            "description": "Look up a value",
            "parameters": {"type": "object", "properties": {}},
            "strict": False,
        }
    ]


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gpt-5.6", True),
        ("o3", True),
        ("chat-latest", False),
        ("gpt-4.1", False),
        ("gpt-4o-mini", False),
        ("gpt-5.3-chat-latest", False),
        ("ft:gpt-4.1-2025-04-14:org:model", False),
        ("omni-moderation-latest", False),
    ],
)
def test_only_reasoning_models_request_encrypted_reasoning(model, expected) -> None:
    result = responses.parameters(model, {}, None, None)

    assert result["store"] is False
    assert (result.get("include") == ["reasoning.encrypted_content"]) is expected


@pytest.mark.parametrize(
    ("model", "credentials", "expected"),
    [
        ("gpt-5.6", {}, True),
        ("gpt-5.6", {"api_protocol": "responses"}, True),
        ("gpt-5.6", {"api_protocol": "chat"}, False),
        ("gpt-audio-1.5", {"api_protocol": "responses"}, False),
        ("gpt-5.5-pro", {"api_protocol": "chat"}, True),
        ("o3-pro", {"api_protocol": "chat"}, True),
    ],
)
def test_endpoint_protocol_routing(model, credentials, expected) -> None:
    assert _uses_responses(model, credentials) is expected


@pytest.mark.parametrize(
    ("model", "credentials", "stream", "selected"),
    [
        ("gpt-5.6", {}, True, "responses_stream"),
        ("gpt-5.6", {}, False, "responses"),
        ("gpt-5.6", {"api_protocol": "chat"}, True, "chat"),
        ("gpt-audio-1.5", {}, False, "chat"),
        ("gpt-5.5-pro", {"api_protocol": "chat"}, False, "responses"),
    ],
)
def test_chat_generation_delegates_to_selected_endpoint(
    model, credentials, stream, selected, llm, mocker, prompt_messages
) -> None:
    mocker.patch.object(llm, "_to_credential_kwargs", return_value={})
    mocker.patch("models.llm.llm.OpenAI")
    targets = {
        "responses_stream": mocker.patch.object(response_stream, "generate"),
        "responses": mocker.patch.object(responses, "generate"),
        "chat": mocker.patch.object(chat, "generate_chat"),
    }
    expected = object()
    targets[selected].return_value = [expected] if stream else expected

    result = llm._chat_generate(
        model, credentials, prompt_messages, {}, None, None, stream, None
    )

    if stream:
        assert list(result) == [expected]
    else:
        assert result is expected
    targets[selected].assert_called_once()
    for name, target in targets.items():
        if name != selected:
            target.assert_not_called()


@pytest.mark.parametrize(
    ("model", "parameters", "expected_parameters", "expected_stream"),
    [
        ("gpt-5.6", {"service_tier": None}, {}, True),
        ("gpt-5.6", {"service_tier": ""}, {}, True),
        ("gpt-5.6", {"service_tier": "priority"}, {"service_tier": "priority"}, True),
        ("gpt-5.6", {"enable_stream": False}, {}, False),
        ("gpt-5.5-pro", {}, {}, False),
        ("gpt-5.5-pro-2026-04-23", {}, {}, False),
        ("gpt-audio-mini", {}, {}, False),
        ("gpt-audio-mini-2025-12-15", {}, {}, False),
        ("o3-pro", {}, {}, False),
    ],
)
def test_invoke_normalizes_tier_and_stream_without_mutating_input(
    model,
    parameters,
    expected_parameters,
    expected_stream,
    llm,
    mocker,
    prompt_messages,
) -> None:
    original = parameters.copy()
    generate = mocker.patch.object(llm, "_chat_generate", return_value=object())

    llm._invoke(model, {}, prompt_messages, parameters, stream=True)

    assert generate.call_args.args[3] == expected_parameters
    assert generate.call_args.args[6] is expected_stream
    assert parameters == original


@pytest.mark.parametrize(
    ("model", "credentials", "endpoint"),
    [
        ("gpt-5.6", {}, "responses"),
        ("gpt-5.6", {"api_protocol": "chat"}, "chat"),
        ("gpt-audio-1.5", {}, "chat"),
        ("gpt-5.5-pro", {"api_protocol": "chat"}, "responses"),
        ("o3-pro", {"api_protocol": "chat"}, "responses"),
    ],
)
def test_credential_validation_uses_the_same_endpoint(
    model, credentials, endpoint, llm, mocker
) -> None:
    client = mocker.patch("models.llm.llm.OpenAI").return_value
    mocker.patch.object(llm, "_to_credential_kwargs", return_value={})

    llm.validate_credentials(model, credentials)

    calls = {
        "responses": client.responses.create,
        "chat": client.chat.completions.create,
    }
    calls[endpoint].assert_called_once()
    for name, call in calls.items():
        if name != endpoint:
            call.assert_not_called()


def test_fine_tuned_model_uses_its_base_schema() -> None:
    assert _base_model("ft:gpt-5.6:team:experiment") == "gpt-5.6"


def test_stream_errors_are_transformed(llm, mocker) -> None:
    source = RuntimeError("stream failed")
    transformed = InvokeBadRequestError("mapped")
    transform = mocker.patch.object(
        llm, "_transform_invoke_error", return_value=transformed
    )

    def broken_stream():
        if False:
            yield None
        raise source

    with pytest.raises(InvokeBadRequestError) as caught:
        list(llm._stream_with_error_mapping(broken_stream()))

    assert caught.value is transformed
    transform.assert_called_once_with(source)
