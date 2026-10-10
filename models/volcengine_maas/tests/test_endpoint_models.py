from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml
from dify_plugin.entities.model import ModelFeature, ModelPropertyKey
from dify_plugin.entities.model.message import AudioPromptMessageContent, UserPromptMessage

from models.client import ArkClientV3
from models.llm.llm import VolcengineMaaSLargeLanguageModel
from models.llm.models import get_v3_req_params


@pytest.mark.parametrize(
    "base_model,max_tokens,efforts,default_effort,has_thinking_switch",
    [
        ("DeepSeek-V4.1-Flash", 393216, ["none", "low", "high", "max"], "high", True),
        ("GLM-5.3-Flash", 131072, ["low", "high", "max"], "max", False),
        ("Doubao-Seed-2.1-lite", 262144, ["minimal", "low", "medium", "high"], "high", True),
    ],
)
def test_endpoint_schema_and_request_parameters(
    base_model, max_tokens, efforts, default_effort, has_thinking_switch
):
    # An arbitrary user model name must resolve through the selected base model.
    credentials = {"base_model_name": base_model, "endpoint_id": "ep-test"}
    llm = VolcengineMaaSLargeLanguageModel([])
    schema = llm.get_customizable_model_schema("my-endpoint", credentials)

    assert schema.model_properties[ModelPropertyKey.CONTEXT_SIZE] == 1048576
    assert schema.model_properties[ModelPropertyKey.MODE] == "chat"
    assert {
        ModelFeature.VISION,
        ModelFeature.VIDEO,
        ModelFeature.TOOL_CALL,
        ModelFeature.MULTI_TOOL_CALL,
        ModelFeature.STREAM_TOOL_CALL,
    }.issubset(schema.features)

    rules = {rule.name: rule for rule in schema.parameter_rules}
    assert rules["max_tokens"].max == max_tokens
    assert rules["reasoning_effort"].options == efforts
    assert rules["reasoning_effort"].default == default_effort
    assert ("thinking" in rules) == has_thinking_switch
    if has_thinking_switch:
        assert rules["thinking"].options == ["enabled", "disabled"]

    assert get_v3_req_params(credentials, {})["max_tokens"] == max_tokens
    for effort in efforts:
        params = get_v3_req_params(credentials, {"reasoning_effort": effort, "max_tokens": 1024})
        assert params["reasoning_effort"] == effort
        assert params["max_tokens"] == 1024
        assert "thinking" not in params


def test_new_models_are_selectable_for_llm_endpoints():
    provider_path = Path(__file__).parents[1] / "provider" / "volcengine_maas.yaml"
    provider = yaml.safe_load(provider_path.read_text(encoding="utf-8"))
    base_model_field = next(
        field for field in provider["model_credential_schema"]["credential_form_schemas"]
        if field["variable"] == "base_model_name"
    )
    for name in ("DeepSeek-V4.1-Flash", "GLM-5.3-Flash", "Doubao-Seed-2.1-lite"):
        options = [option for option in base_model_field["options"] if option["value"] == name]
        assert len(options) == 1
        assert options[0]["show_on"] == [{"variable": "__model_type", "value": "llm"}]


def test_seed_lite_audio_structured_output_and_pricing():
    llm = VolcengineMaaSLargeLanguageModel([])
    schema = llm.get_customizable_model_schema("my-endpoint", {"base_model_name": "Doubao-Seed-2.1-lite"})
    assert ModelFeature.AUDIO in schema.features
    assert ModelFeature.STRUCTURED_OUTPUT in schema.features
    rules = {rule.name: rule for rule in schema.parameter_rules}
    assert rules["response_format"].options == ["text", "json_object", "json_schema"]
    assert "json_schema" in rules
    assert schema.pricing.input == Decimal("0.0008")
    assert schema.pricing.output == Decimal("0.0027")
    assert schema.pricing.unit == Decimal("0.001")
    assert schema.pricing.currency == "RMB"


@pytest.mark.parametrize(
    "audio_fields,expected",
    [
        ({"url": "https://example.com/audio.mp3"}, {"url": "https://example.com/audio.mp3"}),
        ({"base64_data": "YWJj"}, {"data": "YWJj", "format": "mp3"}),
    ],
)
def test_audio_input_is_preserved_in_ark_messages(audio_fields, expected):
    message = UserPromptMessage(content=[
        AudioPromptMessageContent(format="mp3", mime_type="audio/mpeg", **audio_fields),
    ])
    assert ArkClientV3.convert_prompt_message(message) == {
        "role": "user",
        "content": [{"type": "input_audio", "input_audio": expected}],
    }


@pytest.mark.parametrize(
    "base_model,expected_effort",
    [("DeepSeek-V4.1-Flash", "none"), ("Doubao-Seed-2.1-lite", "minimal")],
)
def test_disabling_thinking_uses_the_models_off_effort(monkeypatch, base_model, expected_effort):
    client = Mock()
    client.stream_chat.return_value = iter(())
    monkeypatch.setattr(ArkClientV3, "from_credentials", lambda credentials: client)
    llm = VolcengineMaaSLargeLanguageModel([])
    llm._generate_v3(
        model="my-endpoint",
        credentials={"base_model_name": base_model},
        prompt_messages=[UserPromptMessage(content="hello")],
        model_parameters={"thinking": "disabled", "reasoning_effort": "high"},
        stream=True,
    )
    assert client.stream_chat.call_args.kwargs["thinking"] == {"type": "disabled"}
    assert client.stream_chat.call_args.kwargs["reasoning_effort"] == expected_effort
