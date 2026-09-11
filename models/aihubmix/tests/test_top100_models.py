from pathlib import Path

import yaml


MODEL_DIR = Path(__file__).parents[1] / "models" / "llm"

NEW_MODELS = (
    "auto",
    "gpt-6-astra",
    "gpt-5.6-sol-disc",
    "gpt-5.5-pro",
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite-nothink",
    "gemini-3.1-flash-image",
    "gemini-3.1-flash-lite-image",
    "gemini-3-pro-image",
    "deepseek-v4.1-flash",
    "deepseek-v4-flash-vision-exp",
    "deepseek-v4-flash-0731-fast",
    "coding-glm-5.3",
    "coding-glm-5.2",
    "glm-5.2-fast-preview",
    "qwen3.8-max-2026-09-02",
    "qwen3.8-flash",
    "hy4-preview",
    "hy3-preview",
    "coding-kimi-k3",
    "ernie-5.1",
    "mercury-2.5-preview",
    "mai-thinking-1",
    "agnes-3.0-flash",
    "agnes-2.5-flash",
    "agnes-2.5-pro",
    "agnes-2.5-pro-alpha",
    "ox-alpha",
    "longcat-2.0",
    "muse-spark-1.1",
    "muse-spark-1.2",
    "muse-spark-1.3",
)


def _schema(model: str) -> dict:
    return yaml.safe_load((MODEL_DIR / f"{model}.yaml").read_text(encoding="utf-8"))


def _positions() -> list[str]:
    return yaml.safe_load((MODEL_DIR / "_position.yaml").read_text(encoding="utf-8"))


def test_every_new_model_is_registered() -> None:
    positions = _positions()

    assert len(positions) == len(set(positions))
    for model in NEW_MODELS:
        schema = _schema(model)
        assert schema["model"] == model
        assert schema["model_type"] == "llm"
        assert schema["model_properties"]["mode"] == "chat"
        assert schema["pricing"]["unit"] == "0.000001"
        assert schema["pricing"]["currency"] == "USD"
        assert model in positions


def test_flagship_model_facts() -> None:
    astra = _schema("gpt-6-astra")
    astra_rules = {rule["name"]: rule for rule in astra["parameter_rules"]}

    assert astra["model_properties"]["context_size"] == 1_050_000
    assert astra["pricing"]["input"] == "10"
    assert astra["pricing"]["output"] == "50"
    # "minimal" is rejected by the gateway; "none"/"max" silently degrade.
    assert astra_rules["reasoning_effort"]["options"] == ["low", "medium", "high", "xhigh"]
    assert astra_rules["max_tokens"]["max"] == 128_000
    assert astra_rules["enable_stream"]["type"] == "boolean"

    pro = _schema("gpt-5.5-pro")
    assert pro["model_properties"]["context_size"] == 1_050_000
    assert pro["pricing"]["input"] == "30"
    assert pro["pricing"]["output"] == "180"


def test_ernie_5_1_uses_reasoning_effort_not_boolean_thinking() -> None:
    rules = {rule["name"]: rule for rule in _schema("ernie-5.1")["parameter_rules"]}

    # A boolean `thinking` is rejected upstream with
    # "json: cannot unmarshal bool into struct field ... model.Thinking".
    assert "thinking" not in rules
    assert rules["reasoning_effort"]["options"] == ["none", "low", "medium", "high"]


def test_gemini_image_models_expose_vision() -> None:
    for model in ("gemini-3-pro-image", "gemini-3.1-flash-image", "gemini-3.1-flash-lite-image"):
        assert "vision" in _schema(model)["features"], model


def test_gemini_nothink_variant_has_no_agent_thought() -> None:
    schema = _schema("gemini-3.1-flash-lite-nothink")

    assert "agent-thought" not in schema["features"]


def test_no_free_tier_models_remain() -> None:
    # Free-tier aliases share a single shared quota and fail once it is exhausted,
    # so they are not exposed as predefined models.
    assert [m for m in _positions() if m.endswith("-free")] == []
    assert list(MODEL_DIR.glob("*-free.yaml")) == []


def test_retired_models_are_gone() -> None:
    retired = (
        "gpt-4.5-preview",
        "gemini-2.0-flash",
        "gemini-2.5-flash-preview-04-17",
        "gemini-2.5-flash-preview-04-17-nothink",
        "deepseek-v3.2-speciale",
        "deepseek-r1-aihubmix",
        "Llama-3-3-70B-Instruct-aihubmix",
        "deepSeek-V3-0324",
        "llama-4-maverick-17b-128e-instruct-fp8",
        "llama-4-scout-17b-16e-instruct",
        "llama-4-scout-17b-16e-instruct-meta-llama",
    )
    positions = _positions()
    for model in retired:
        assert not (MODEL_DIR / f"{model}.yaml").exists(), model
        assert model not in positions, model
