from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity, ModelFeature, ModelPropertyKey
from models.llm.llm import GoogleLargeLanguageModel
from models.llm.model_schema import (
    INLINE_FILE_PARAMETER_NAME,
    model_accepts_file_inputs,
)


LLM_SCHEMA_DIR = Path(__file__).parents[1] / "llm"
LATEST_FLASH_MODELS = (
    ("gemini-3.7-flash", "Medium", Decimal("0.75"), Decimal("3.75")),
    ("gemini-3.6-flash", "Medium", Decimal("0.75"), Decimal("3.75")),
    ("gemini-3.5-flash-lite", "Minimal", Decimal("0.30"), Decimal("2.50")),
)

# 3.6 and 3.7 Flash are published on one introductory rate card: $0.75 in /
# $3.75 out per 1M tokens through 2026-12-31, doubling on 2027-01-01.
# https://ai.google.dev/gemini-api/docs/pricing
INTRODUCTORY_FLASH_MODELS = ("gemini-3.6-flash", "gemini-3.7-flash")


def _load_llm_model_schemas() -> list[AIModelEntity]:
    schemas = []
    for path in LLM_SCHEMA_DIR.glob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            schemas.append(AIModelEntity(**data))
    return schemas


def test_inline_file_parameter_is_runtime_schema_not_yaml_duplication():
    for path in LLM_SCHEMA_DIR.glob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        rules = data.get("parameter_rules") or []
        assert INLINE_FILE_PARAMETER_NAME not in {rule.get("name") for rule in rules}


def test_inline_file_parameter_is_injected_for_all_file_input_models():
    llm = GoogleLargeLanguageModel(_load_llm_model_schemas())

    for schema in llm.predefined_models():
        rule_names = {rule.name for rule in schema.parameter_rules}
        has_inline_file = INLINE_FILE_PARAMETER_NAME in rule_names
        assert has_inline_file == model_accepts_file_inputs(schema), schema.model


def test_inline_file_parameter_covers_newer_gemini_models_without_yaml_edits():
    llm = GoogleLargeLanguageModel(_load_llm_model_schemas())

    pro_31 = llm.get_model_schema("gemini-3.1-pro-preview")
    assert pro_31 is not None
    assert INLINE_FILE_PARAMETER_NAME in {rule.name for rule in pro_31.parameter_rules}

    text_only = llm.get_model_schema("gemini-pro")
    assert text_only is not None
    assert INLINE_FILE_PARAMETER_NAME not in {
        rule.name for rule in text_only.parameter_rules
    }


@pytest.mark.parametrize(
    ("model", "thinking_level", "input_price", "output_price"),
    LATEST_FLASH_MODELS,
)
def test_latest_flash_model_contract(
    model: str,
    thinking_level: str,
    input_price: Decimal,
    output_price: Decimal,
):
    llm = GoogleLargeLanguageModel(_load_llm_model_schemas())
    schema = llm.get_model_schema(model)
    assert schema is not None

    assert schema.model_properties[ModelPropertyKey.CONTEXT_SIZE] == 1_048_576
    assert {
        ModelFeature.TOOL_CALL,
        ModelFeature.MULTI_TOOL_CALL,
        ModelFeature.STREAM_TOOL_CALL,
        ModelFeature.VISION,
        ModelFeature.DOCUMENT,
        ModelFeature.VIDEO,
        ModelFeature.AUDIO,
        ModelFeature.STRUCTURED_OUTPUT,
    } <= set(schema.features or [])

    rules = {rule.name: rule for rule in schema.parameter_rules}
    assert not {"temperature", "top_p", "top_k"} & rules.keys()
    assert rules["include_thoughts"].default is False
    assert rules["media_resolution"].options == ["Default", "Low", "Medium", "High"]
    assert rules["thinking_level"].default == thinking_level
    expected_thinking_levels = (
        ["Low", "Medium", "High"]
        if model == "gemini-3.7-flash"
        else ["Minimal", "Low", "Medium", "High"]
    )
    assert rules["thinking_level"].options == expected_thinking_levels
    assert rules["max_output_tokens"].default == 65_536
    assert rules["max_output_tokens"].max == 65_536
    assert rules["service_tier"].default == "standard"
    assert rules["service_tier"].options == ["flex", "standard", "priority"]
    assert schema.pricing is not None
    assert schema.pricing.input == input_price
    assert schema.pricing.output == output_price
    assert schema.pricing.unit == Decimal("0.000001")
    assert schema.pricing.currency == "USD"


def test_introductory_flash_models_share_one_rate_card():
    # The two models on the introductory schedule move together: same price
    # today, same doubling on 2027-01-01. Pinning them to each other rather
    # than only to literals means one of them cannot quietly carry the
    # post-promotion number while the other still carries the current one.
    llm = GoogleLargeLanguageModel(_load_llm_model_schemas())
    pricings = []
    for model in INTRODUCTORY_FLASH_MODELS:
        schema = llm.get_model_schema(model)
        assert schema is not None, model
        assert schema.pricing is not None, model
        pricings.append((schema.pricing.input, schema.pricing.output))

    assert len(set(pricings)) == 1, dict(zip(INTRODUCTORY_FLASH_MODELS, pricings))


def test_latest_flash_models_are_first_in_display_order():
    position = yaml.safe_load((LLM_SCHEMA_DIR / "_position.yaml").read_text())
    assert position[:4] == [
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
    ]
