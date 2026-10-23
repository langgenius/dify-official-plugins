import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from dify_plugin.entities.model.message import UserPromptMessage

llm_mod = importlib.import_module("models.llm.llm")
Model = llm_mod.BedrockLargeLanguageModel

@pytest.mark.parametrize("model_id", ["anthropic.claude-haiku-5-5", "global.anthropic.claude-haiku-5-5", "us.anthropic.claude-haiku-5-5", "eu.anthropic.claude-haiku-5-5", "au.anthropic.claude-haiku-5-5", "jp.anthropic.claude-haiku-5-5"])
def test_custom_profile_hides_unsupported_controls(model_id):
    names = ["model_name", "temperature", "top_p", "top_k", "reasoning_type", "reasoning_budget", "max_tokens", "response_format"]
    schema = SimpleNamespace(model="anthropic claude", parameter_rules=[SimpleNamespace(name=name) for name in names])
    assert [rule.name for rule in Model._get_inference_profile_parameter_rules(None, schema, model_id)] == ["max_tokens", "response_format"]

@pytest.mark.parametrize("underlying", [False, True])
def test_actual_converse_request_drops_stale_values(underlying):
    client = MagicMock(); client.converse.side_effect = RuntimeError("request captured")
    instance = object.__new__(Model)
    info = {"model": "global.anthropic.claude-haiku-5-5", "support_system_prompts": True, "support_tool_use": True}
    if underlying:
        info.update(model="arn:aws:bedrock:us-east-1:123456789012:application-inference-profile/example", underlying_model_id="anthropic.claude-haiku-5-5")
    params = {"max_tokens": 4096, "temperature": 0.7, "top_p": 1, "top_k": 50, "reasoning_type": True, "reasoning_budget": 2048}
    with patch.object(llm_mod, "get_bedrock_client", return_value=client), pytest.raises(RuntimeError, match="request captured"):
        instance._generate_with_converse(info, {}, [UserPromptMessage(content="hello")], params, stream=False)
    request = client.converse.call_args.kwargs
    assert request["inferenceConfig"] == {"maxTokens": 4096}
    assert request["additionalModelRequestFields"] == {}
    assert "additionalModelResponseFieldPaths" not in request

def test_legacy_haiku_keeps_sampling_rules():
    names = ["model_name", "temperature", "top_p", "top_k", "reasoning_type", "reasoning_budget", "max_tokens"]
    schema = SimpleNamespace(model="anthropic claude", parameter_rules=[SimpleNamespace(name=name) for name in names])
    assert [rule.name for rule in Model._get_inference_profile_parameter_rules(None, schema, "anthropic.claude-haiku-4-5-20251001-v1:0")] == names[1:]
