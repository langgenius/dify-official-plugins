"""Public SDK invoke -> compatibility adapter -> mocked HTTP boundary tests."""

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import PromptMessageTool, UserPromptMessage
from dify_plugin.errors.model import InvokeBadRequestError

from models.llm._legacy_parameters import CONTRACTS, TRANSPORT_FIELDS
from models.llm.llm import TokenerLargeLanguageModel


def instance(*models):
    return TokenerLargeLanguageModel(
        model_schemas=[
            AIModelEntity.model_validate(
                yaml.safe_load(Path(f"models/llm/{model}.yaml").read_text())
            )
            for model in models
        ]
    )


def respond(_url, **kwargs):
    body = json.loads(kwargs["data"])
    result = requests.Response()
    result.status_code = 200
    if body["stream"]:
        result._content = (
            b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}],'
            b'"usage":{"prompt_tokens":2,"completion_tokens":1}}\n\ndata: [DONE]\n\n'
        )
        result._content_consumed = True
    else:
        result._content = json.dumps(
            {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            }
        ).encode()
    return result


def invoke_body(model, parameters, *, stream=False, tools=None, native=False, google_openai=False):
    original = deepcopy(parameters)
    runtime = instance(model)
    with (
        patch("requests.post", side_effect=respond) as post,
        patch("models.llm.llm.GEMINI_NATIVE_TRANSPORT_CONFIRMED", native),
        patch("models.llm.llm.GEMINI_GOOGLE_OPENAI_TRANSPORT_CONFIRMED", google_openai),
    ):
        chunks = list(
            runtime.invoke(
                model,
                {"api_key": "OFFLINE_ONLY"},
                [UserPromptMessage(content="offline integration")],
                parameters,
                tools=tools,
                stream=stream,
            )
        )
    post.assert_called_once()
    assert parameters == original
    assert any(chunk.delta.message.content == "ok" for chunk in chunks)
    assert chunks[-1].delta.usage.prompt_tokens == 2
    assert chunks[-1].delta.usage.completion_tokens == 1
    body = json.loads(post.call_args.kwargs["data"])
    assert "compatibility_inputs" not in body
    assert "sdk_parameters" not in body
    assert "wire_overrides" not in body
    return body


@pytest.mark.parametrize("model", CONTRACTS["qwen_thinking_models"])
@pytest.mark.parametrize("stream", [False, True])
def test_public_qwen_false_reaches_http_unchanged(model, stream):
    body = invoke_body(model, {"enable_thinking": False, "max_tokens": 256}, stream=stream)
    assert body["enable_thinking"] is False
    assert body["max_tokens"] == 256
    assert "extra_body" not in body


@pytest.mark.parametrize("model", CONTRACTS["reasoning_effort_options"])
def test_public_effort_from_original_provider_reaches_http(model):
    effort = CONTRACTS["reasoning_effort_options"][model][0]
    body = invoke_body(model, {"reasoning_effort": effort, "max_tokens": 256})
    assert body["reasoning_effort"] == effort


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("enable", [False, True])
def test_public_stream_control_is_local_and_usage_request_follows_actual_stream(stream, enable):
    body = invoke_body(
        "gpt-5-nano",
        {"max_tokens": 256, "enable_stream": enable, "reasoning_effort": "minimal"},
        stream=stream,
    )
    assert body["stream"] is (stream and enable)
    assert "enable_stream" not in body
    if body["stream"]:
        assert body["stream_options"] == {"include_usage": True}
    else:
        assert "stream_options" not in body


@pytest.mark.parametrize("model", CONTRACTS["gemini_models"])
def test_public_gemini_alias_works_without_any_diagnostic_target_cap(model):
    body = invoke_body(model, {"max_output_tokens": 256})
    assert body["max_tokens"] == 256
    assert "max_output_tokens" not in body


def test_public_gemini_native_config_preserves_false_zero_and_exact_level():
    body = invoke_body(
        "gemini-3-flash-preview",
        {
            "max_output_tokens": 256,
            "temperature": 0,
            "top_p": 0,
            "include_thoughts": False,
            "thinking_level": "Minimal",
        },
        native=True,
    )
    assert body["temperature"] == body["top_p"] == 0
    assert body["extra_body"] == {
        "generationConfig": {
            "thinkingConfig": {
                "includeThoughts": False,
                "thinkingLevel": "minimal",
            }
        }
    }
    assert "thinking_level" not in body
    assert "include_thoughts" not in body


def test_public_gate_rejects_unconfirmed_native_contract_before_http():
    runtime = instance("gemini-3-flash-preview")
    with (
        patch("requests.post") as post,
        pytest.raises(InvokeBadRequestError, match="not confirmed"),
    ):
        list(
            runtime.invoke(
                "gemini-3-flash-preview",
                {"api_key": "OFFLINE_ONLY"},
                [UserPromptMessage(content="test")],
                {"thinking_level": "Minimal"},
                stream=False,
            )
        )
    post.assert_not_called()


@pytest.mark.parametrize("model,contract", CONTRACTS["gemini_models"].items())
@pytest.mark.parametrize("stream", [False, True])
def test_public_google_openai_uses_exact_proxy_nesting_and_source_controls(model, contract, stream):
    parameters = {
        "include_thoughts": False,
        "max_output_tokens": 256,
        "grounding": False,
        "url_context": False,
        "code_execution": False,
    }
    expected = {"include_thoughts": False}
    if "thinking_levels" in contract:
        level = contract["thinking_levels"][0]
        parameters["thinking_level"] = level
        expected["thinking_level"] = level.lower()
    else:
        parameters["thinking_mode"] = False
        expected["thinking_budget"] = 0
    if contract.get("media_resolution"):
        parameters["media_resolution"] = "Default"
    body = invoke_body(model, parameters, google_openai=True, stream=stream)
    assert body["extra_body"] == {"extra_body": {"google": {"thinking_config": expected}}}
    assert body["max_tokens"] == 256
    assert "generationConfig" not in json.dumps(body)
    assert "reasoning_effort" not in body
    assert "include_thoughts" not in body
    assert "media_resolution" not in body
    assert not ({"grounding", "url_context", "code_execution"} & body.keys())


@pytest.mark.parametrize("tier", ["standard", "flex", "priority"])
def test_public_google_openai_service_tier_is_supported_top_level(tier):
    body = invoke_body(
        "gemini-3.1-flash-lite",
        {"service_tier": tier, "max_output_tokens": 256},
        google_openai=True,
    )
    if tier == "standard":
        assert "service_tier" not in body
    else:
        assert body["service_tier"] == tier


def test_public_google_openai_flex_source_alias_keeps_true_false_semantics():
    body = invoke_body("gemini-2.5-flash", {"flex_inference": True}, google_openai=True)
    assert body["service_tier"] == "flex"
    body = invoke_body("gemini-2.5-flash", {"flex_inference": False}, google_openai=True)
    assert "service_tier" not in body


@pytest.mark.parametrize("model", CONTRACTS["gemini_models"])
@pytest.mark.parametrize("stream", [False, True])
def test_public_gemini_standalone_source_schema_becomes_explicit_response_format(model, stream):
    source_schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }
    body = invoke_body(
        model,
        {"json_schema": json.dumps(source_schema), "max_output_tokens": 256},
        google_openai=True,
        stream=stream,
    )
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "dify_legacy_schema",
            "schema": source_schema,
        },
    }
    assert "json_schema" not in body


@pytest.mark.parametrize("value", [None, ""])
def test_public_gemini_empty_source_schema_means_json_object(value):
    body = invoke_body("gemini-3-flash-preview", {"json_schema": value}, google_openai=True)
    assert body["response_format"] == {"type": "json_object"}


def test_public_gemini_explicit_native_response_format_keeps_native_schema_wrapper():
    native_schema = {"name": "native", "schema": {"type": "object"}, "strict": True}
    body = invoke_body(
        "gemini-3-flash-preview",
        {"response_format": "json_schema", "json_schema": json.dumps(native_schema)},
        google_openai=True,
    )
    assert body["response_format"] == {"type": "json_schema", "json_schema": native_schema}


@pytest.mark.parametrize(
    "value", ["not-json", "[]", "true", '{"minimum": NaN}', {"type": "object"}]
)
def test_public_gemini_invalid_source_schema_is_rejected_before_http(value):
    with patch("requests.post") as post, pytest.raises(InvokeBadRequestError, match="json_schema"):
        list(
            instance("gemini-3-flash-preview").invoke(
                "gemini-3-flash-preview",
                {"api_key": "OFFLINE_ONLY"},
                [],
                {"json_schema": value},
                stream=False,
            )
        )
    post.assert_not_called()


def test_public_gemini_source_schema_custom_tools_is_explicitly_unsupported():
    tool = PromptMessageTool(
        name="lookup", description="lookup", parameters={"type": "object", "properties": {}}
    )
    with patch("requests.post") as post, pytest.raises(InvokeBadRequestError, match="custom tools"):
        list(
            instance("gemini-3-flash-preview").invoke(
                "gemini-3-flash-preview",
                {"api_key": "OFFLINE_ONLY"},
                [],
                {"json_schema": '{"type":"object"}'},
                tools=[tool],
                stream=False,
            )
        )
    post.assert_not_called()


@pytest.mark.parametrize(
    "parameters",
    [
        {"media_resolution": "High"},
        {"grounding": True},
        {"url_context": True},
        {"code_execution": True},
    ],
)
def test_public_google_openai_unsupported_native_feature_never_sends(parameters):
    with (
        patch("models.llm.llm.GEMINI_GOOGLE_OPENAI_TRANSPORT_CONFIRMED", True),
        patch("requests.post") as post,
        pytest.raises(InvokeBadRequestError, match="not supported"),
    ):
        list(
            instance("gemini-3-flash-preview").invoke(
                "gemini-3-flash-preview", {"api_key": "OFFLINE_ONLY"}, [], parameters, stream=False
            )
        )
    post.assert_not_called()


def test_public_custom_tools_consume_native_toggles_before_gate_or_conflict_check():
    tool = PromptMessageTool(
        name="lookup", description="lookup", parameters={"type": "object", "properties": {}}
    )
    body = invoke_body(
        "gemini-3-flash-preview",
        {
            "grounding": True,
            "url_context": True,
            "code_execution": True,
            "max_output_tokens": 256,
        },
        tools=[tool],
        native=False,
    )
    assert body["tools"][0]["function"]["name"] == "lookup"
    assert all(item.get("type") == "function" for item in body["tools"])
    assert not ({"grounding", "url_context", "code_execution"} & body.keys())


def test_public_native_tool_is_converted_only_with_confirmed_contract():
    body = invoke_body(
        "gemini-3-flash-preview", {"grounding": True, "max_output_tokens": 256}, native=True
    )
    assert body["tools"] == [{"googleSearch": {}}]


@pytest.mark.parametrize(
    "parameters",
    [
        {"max_output_tokens": 256, "max_tokens": 512},
        {"max_output_tokens": 256, "unknown_parameter": True},
        {"max_output_tokens": 999999999},
    ],
)
def test_public_conflicting_or_unknown_or_out_of_model_range_input_never_sends(parameters):
    with patch("requests.post") as post, pytest.raises((ValueError, InvokeBadRequestError)):
        list(
            instance("gemini-3-flash-preview").invoke(
                "gemini-3-flash-preview", {"api_key": "OFFLINE_ONLY"}, [], parameters, stream=False
            )
        )
    post.assert_not_called()


@pytest.mark.parametrize("name", sorted(TRANSPORT_FIELDS))
def test_public_user_transport_overrides_never_reach_http(name):
    with patch("requests.post") as post, pytest.raises(InvokeBadRequestError):
        list(
            instance("gpt-4o-mini").invoke(
                "gpt-4o-mini",
                {"api_key": "OFFLINE_ONLY"},
                [],
                {name: "SECRET_NOT_FOR_LOGS"},
                stream=False,
            )
        )
    post.assert_not_called()


def test_default_native_builtin_sampling_keeps_preexisting_sdk_filter_behavior():
    body = invoke_body("gpt-5.6-luna", {"temperature": 0.2, "top_p": 0.3, "max_tokens": 256})
    assert body["max_tokens"] == 256
    assert "temperature" not in body and "top_p" not in body


@pytest.mark.parametrize("model", CONTRACTS["native_sdk_filtered_sampling_models"])
@pytest.mark.parametrize(
    "controls",
    [
        {"reasoning_effort": "low"},
        {"enable_stream": False},
        {"reasoning_effort": "low", "enable_stream": True},
    ],
)
def test_native_builtin_sampling_keeps_sdk_behavior_with_compatibility_controls(model, controls):
    parameters = {"temperature": 0.2, "top_p": 0.3, "max_tokens": 256, **controls}
    body = invoke_body(model, parameters, stream=True)
    assert "temperature" not in body and "top_p" not in body
    assert body["max_tokens"] == 256
    if "reasoning_effort" in controls:
        assert body["reasoning_effort"] == "low"
    assert body["stream"] is (controls.get("enable_stream") is not False)
    with patch("requests.post") as post, pytest.raises(InvokeBadRequestError, match="no reviewed"):
        list(
            instance(model).invoke(
                model,
                {"api_key": "OFFLINE_ONLY"},
                [],
                {**parameters, "unknown_sampling": 0.2},
                stream=False,
            )
        )
    post.assert_not_called()


def test_interleaved_public_calls_have_request_local_flags_and_no_mutation():
    runtime = instance("qwen3.5-plus")
    inputs = [{"max_tokens": 256, "enable_thinking": bool(index % 2)} for index in range(12)]
    originals = deepcopy(inputs)
    observed = {}

    def capture(url, **kwargs):
        body = json.loads(kwargs["data"])
        observed[int(body["messages"][0]["content"])] = body["enable_thinking"]
        return respond(url, **kwargs)

    def run(index):
        return list(
            runtime.invoke(
                "qwen3.5-plus",
                {"api_key": "OFFLINE_ONLY"},
                [UserPromptMessage(content=str(index))],
                inputs[index],
                stream=False,
            )
        )

    with patch("requests.post", side_effect=capture), ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, range(12)))
    assert len(results) == 12
    assert observed == {index: bool(index % 2) for index in range(12)}
    assert inputs == originals
    assert not hasattr(runtime, "compatibility_inputs")
    assert not hasattr(runtime, "legacy_parameter_plan")
