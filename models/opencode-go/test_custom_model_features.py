"""Customizable model form: display name + capability toggles (no network)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import dify_plugin  # noqa: E402,F401
from dify_plugin.entities.model import ModelFeature  # noqa: E402
from models.llm.llm import OpenCodeGoLargeLanguageModel  # noqa: E402


def make_model() -> OpenCodeGoLargeLanguageModel:
    return OpenCodeGoLargeLanguageModel(model_schemas=[])


def feature_values(schema) -> set[str]:
    return {f.value if hasattr(f, "value") else str(f) for f in (schema.features or [])}


def rule_names(schema) -> set[str]:
    return {r.name for r in (schema.parameter_rules or [])}


def test_display_name_used_as_label() -> None:
    schema = make_model().get_customizable_model_schema(
        "kimi-k2.6",
        {"display_name": "Kimi K2.6 (Work)"},
    )
    assert schema is not None
    assert schema.model == "kimi-k2.6"
    assert schema.label.en_us == "Kimi K2.6 (Work)"
    assert schema.label.zh_hans == "Kimi K2.6 (Work)"


def test_display_name_defaults_to_model_id() -> None:
    schema = make_model().get_customizable_model_schema("kimi-k2.6", {})
    assert schema is not None
    assert schema.label.en_us == "kimi-k2.6"


def test_thinking_on_by_default_adds_agent_thought_and_params() -> None:
    schema = make_model().get_customizable_model_schema("custom-model", {})
    assert schema is not None
    feats = feature_values(schema)
    assert ModelFeature.AGENT_THOUGHT.value in feats
    names = rule_names(schema)
    assert "enable_thinking" in names
    assert "thinking_budget" in names
    assert "reasoning_effort" in names


def test_thinking_off_removes_agent_thought_and_params() -> None:
    schema = make_model().get_customizable_model_schema(
        "custom-model", {"thinking_support": "false"}
    )
    assert schema is not None
    feats = feature_values(schema)
    assert ModelFeature.AGENT_THOUGHT.value not in feats
    names = rule_names(schema)
    assert "enable_thinking" not in names


def test_multimodal_toggles() -> None:
    schema = make_model().get_customizable_model_schema(
        "custom-model",
        {
            "vision_support": "true",
            "audio_support": "true",
            "video_support": "true",
            "document_support": "true",
        },
    )
    assert schema is not None
    feats = feature_values(schema)
    assert ModelFeature.VISION.value in feats
    assert ModelFeature.AUDIO.value in feats
    assert ModelFeature.VIDEO.value in feats
    assert ModelFeature.DOCUMENT.value in feats


def test_structured_output_adds_feature_and_params() -> None:
    schema = make_model().get_customizable_model_schema(
        "custom-model",
        {"structured_output_support": "true", "thinking_support": "false"},
    )
    assert schema is not None
    feats = feature_values(schema)
    assert ModelFeature.STRUCTURED_OUTPUT.value in feats
    names = rule_names(schema)
    assert "response_format" in names
    assert "json_schema" in names
    assert "enable_thinking" not in names


def test_tool_call_default_and_off() -> None:
    on = make_model().get_customizable_model_schema("m", {})
    off = make_model().get_customizable_model_schema(
        "m", {"function_calling_type": "no_call"}
    )
    assert on is not None and off is not None
    assert ModelFeature.TOOL_CALL.value in feature_values(on)
    assert ModelFeature.TOOL_CALL.value not in feature_values(off)


def main() -> int:
    tests = [
        test_display_name_used_as_label,
        test_display_name_defaults_to_model_id,
        test_thinking_on_by_default_adds_agent_thought_and_params,
        test_thinking_off_removes_agent_thought_and_params,
        test_multimodal_toggles,
        test_structured_output_adds_feature_and_params,
        test_tool_call_default_and_off,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError:
            failed += 1
            print(f"FAIL  {fn.__name__}")
            import traceback

            traceback.print_exc()
    print(f"\nDONE failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
