from unittest.mock import patch

import pytest
from dify_plugin.entities.model import ModelFeature
from dify_plugin.entities.model.message import SystemPromptMessage, UserPromptMessage

from models.llm.llm import OpenAILargeLanguageModel

BASE_INVOKE = (
    "dify_plugin.interfaces.model.openai_compatible.llm."
    "OAICompatLargeLanguageModel._invoke"
)
BASE_CREDENTIALS = {
    "endpoint_url": "https://api.example.com/v1/",
    "api_key": "test-key",
    "mode": "chat",
    "agent_thought_support": "supported",
    "compatibility_mode": "strict",
}


@pytest.mark.parametrize("mode", ["supported", "native"])
def test_enabled_structured_output_modes_advertise_capability(mode: str):
    model = OpenAILargeLanguageModel(model_schemas=[])

    schema = model.get_customizable_model_schema(
        "test-model",
        {**BASE_CREDENTIALS, "structured_output_support": mode},
    )

    assert ModelFeature.STRUCTURED_OUTPUT in schema.features
    parameter_names = [rule.name for rule in schema.parameter_rules]
    assert "response_format" in parameter_names
    assert "json_schema" in parameter_names


def test_disabled_structured_output_does_not_advertise_capability():
    model = OpenAILargeLanguageModel(model_schemas=[])

    schema = model.get_customizable_model_schema(
        "test-model",
        {**BASE_CREDENTIALS, "structured_output_support": "not_supported"},
    )

    assert ModelFeature.STRUCTURED_OUTPUT not in schema.features


def test_legacy_supported_mode_uses_prompt_and_json_object_transport():
    model = OpenAILargeLanguageModel(model_schemas=[])
    prompt_messages = [
        SystemPromptMessage(content="You are helpful."),
        UserPromptMessage(content="Return an answer."),
    ]
    model_parameters = {
        "response_format": "json_schema",
        "json_schema": '{"type":"object","properties":{"answer":{"type":"string"}}}',
    }

    with patch(BASE_INVOKE, return_value=object()) as base_invoke:
        model._invoke(
            model="test-model",
            credentials={**BASE_CREDENTIALS, "structured_output_support": "supported"},
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            stream=False,
        )

    forwarded_messages = base_invoke.call_args.args[2]
    forwarded_parameters = base_invoke.call_args.args[3]
    assert forwarded_parameters["response_format"] == "json_object"
    assert "json_schema" not in forwarded_parameters
    assert "JSON Schema:" in forwarded_messages[0].content
    assert forwarded_messages[0].content.endswith("You are helpful.")


def test_native_mode_preserves_json_schema_transport_without_prompt_injection():
    model = OpenAILargeLanguageModel(model_schemas=[])
    prompt_messages = [SystemPromptMessage(content="You are helpful.")]
    json_schema = '{"type":"object","properties":{"answer":{"type":"string"}}}'
    model_parameters = {
        "response_format": "json_schema",
        "json_schema": json_schema,
    }

    with patch(BASE_INVOKE, return_value=object()) as base_invoke:
        model._invoke(
            model="test-model",
            credentials={**BASE_CREDENTIALS, "structured_output_support": "native"},
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            stream=False,
        )

    forwarded_messages = base_invoke.call_args.args[2]
    forwarded_parameters = base_invoke.call_args.args[3]
    assert forwarded_parameters["response_format"] == "json_schema"
    assert forwarded_parameters["json_schema"] == json_schema
    assert forwarded_messages[0].content == "You are helpful."
