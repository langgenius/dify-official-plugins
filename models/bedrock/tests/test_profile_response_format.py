import importlib
from unittest.mock import MagicMock, patch

import pytest
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    SystemPromptMessage,
    UserPromptMessage,
)

mod = importlib.import_module("models.llm.llm")
Model = mod.BedrockLargeLanguageModel

@pytest.mark.parametrize("entrypoint", ["_invoke", "_code_block_mode_wrapper"])
@pytest.mark.parametrize("model_id", ["anthropic.claude-sonnet-4-6", "anthropic.claude-opus-4-6-v1", "anthropic.claude-haiku-5-5", "anthropic.claude-sonnet-5-5", "anthropic.claude-4-6-sonnet", "global.anthropic.claude-opus-5-5"])
def test_modern_profile_does_not_append_assistant_prefill(model_id, entrypoint):
    instance = object.__new__(Model)
    instance._get_model_info = MagicMock(return_value={"model": "profile"})
    instance._generate_with_converse = MagicMock(return_value="ok")
    messages = [SystemPromptMessage(content="Answer in JSON"), UserPromptMessage(content="hello")]
    with patch.object(mod, "get_inference_profile_info", return_value={"models": [{"modelArn": f"arn:aws:bedrock:us-east-1::foundation-model/{model_id}"}]}):
        assert getattr(instance, entrypoint)("custom", {"inference_profile_id": "profile"}, messages, {"response_format": "json"}) == "ok"
    actual = instance._generate_with_converse.call_args.args[2]
    assert isinstance(actual[-1], UserPromptMessage)
    assert "Answer in JSON" in actual[0].content
    assert "valid json" in actual[0].content

def invoke_profile(messages, params, model_id="anthropic.claude-sonnet-4-6"):
    instance = object.__new__(Model)
    instance._get_model_info = MagicMock(return_value={"model": "profile"})
    instance._generate_with_converse = MagicMock(return_value="ok")
    with patch.object(mod, "get_inference_profile_info", return_value={"models": [{"modelArn": f"arn:aws:bedrock:us-east-1::foundation-model/{model_id}"}]}):
        instance._invoke("custom", {"inference_profile_id": "profile"}, messages, params)
    return instance._generate_with_converse.call_args.args[2]

def test_legacy_profile_keeps_prefill():
    actual = invoke_profile([UserPromptMessage(content="hello")], {"response_format": "json"}, "anthropic.claude-3-sonnet-20240229-v1:0")
    assert isinstance(actual[-1], AssistantPromptMessage)

def test_no_system_does_not_duplicate_user_prompt():
    actual = invoke_profile([UserPromptMessage(content="private-user-question")], {"response_format": "json"})
    assert "private-user-question" not in actual[0].content
    assert actual[-1].content == "private-user-question"

def test_native_schema_keeps_precedence():
    schema = {"type": "object"}; params = {"response_format": "json", "json_schema": schema}
    actual = invoke_profile([UserPromptMessage(content="hello")], params)
    assert params == {"_structured_output_schema": schema}
    assert len(actual) == 1
