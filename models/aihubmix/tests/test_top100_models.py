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


def _rule(model: str, name: str) -> dict:
    for rule in _schema(model)["parameter_rules"]:
        if rule["name"] == name:
            return rule
    raise AssertionError(f"{model} has no {name} rule")


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
    assert astra_rules["reasoning_effort"]["options"] == ["low", "medium", "high", "xhigh", "max"]
    assert astra_rules["max_tokens"]["max"] == 128_000
    assert astra_rules["enable_stream"]["type"] == "boolean"

    pro = _schema("gpt-5.5-pro")
    pro_rules = {rule["name"]: rule for rule in pro["parameter_rules"]}
    assert pro["model_properties"]["context_size"] == 1_050_000
    assert pro["pricing"]["input"] == "30"
    assert pro["pricing"]["output"] == "180"
    # gpt-5.5-pro has no openai.chat_completions surface in the projection and is a
    # reasoning-only model: the gateway answers 200 to `temperature` but drops it.
    assert "temperature" not in pro_rules
    assert "top_p" not in pro_rules
    assert pro_rules["reasoning_effort"]["options"] == ["medium", "high", "xhigh"]


def test_ernie_5_1_uses_reasoning_effort_not_boolean_thinking() -> None:
    rules = {rule["name"]: rule for rule in _schema("ernie-5.1")["parameter_rules"]}

    # A boolean `thinking` is rejected upstream with
    # "json: cannot unmarshal bool into struct field ... model.Thinking".
    assert "thinking" not in rules
    # The projection lists only a thinking_budget for ernie-5.1 and gives it no provable
    # upper bound, but reasoning_effort is verified to work on the gateway, so it stays.
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


# --- Gemini image models -----------------------------------------------------
#
# `llm.py` routes every `gemini*` id to `GoogleLargeLanguageModel`, and that
# class only emits `responseModalities: [TEXT, IMAGE]` / `imageConfig` for ids
# listed in `IMAGE_GENERATION_MODELS`. An image model missing from that set is
# silently text-only, so the allowlist and the YAML options are asserted here.

IMAGE_MODELS = (
    "gemini-3-pro-image",
    "gemini-3.1-flash-image",
    "gemini-3.1-flash-lite-image",
)


def _google_source() -> str:
    return (MODEL_DIR / "google.py").read_text(encoding="utf-8")


def test_image_models_are_in_the_generation_allowlist() -> None:
    block = _google_source().split("IMAGE_GENERATION_MODELS = {", 1)[1].split("}", 1)[0]
    for model in IMAGE_MODELS:
        assert f'"{model}"' in block, model


def test_image_models_expose_validated_aspect_ratios() -> None:
    # Live-probed against the gateway: only the 3.1 Flash Image pair renders the
    # ultra-wide ratios; gemini-3-pro-image answers 400 for them.
    base = ["Auto", "1:1", "9:16", "16:9", "3:4", "4:3", "3:2", "2:3", "5:4", "4:5", "21:9"]
    expected = {
        "gemini-3-pro-image": base,
        "gemini-3.1-flash-image": base + ["4:1", "8:1"],
        "gemini-3.1-flash-lite-image": base + ["4:1", "8:1"],
    }
    for model, options in expected.items():
        rule = _rule(model, "aspect_ratio")
        assert rule["options"] == options, model
        assert rule["default"] == "Auto", model


def test_image_models_expose_validated_resolutions() -> None:
    # Flash-Lite renders 1K only; 2K and 4K come back as an upstream 400.
    expected = {
        "gemini-3-pro-image": ["1K", "2K", "4K"],
        "gemini-3.1-flash-image": ["1K", "2K", "4K"],
        "gemini-3.1-flash-lite-image": ["1K"],
    }
    for model, options in expected.items():
        assert _rule(model, "resolution")["options"] == options, model


def test_image_models_have_no_inert_thinking_switch() -> None:
    # `_set_thinking_config` returns early for IMAGE_GENERATION_MODELS, so an
    # `include_thoughts` rule would render a control that does nothing.
    for model in IMAGE_MODELS:
        names = {rule["name"] for rule in _schema(model)["parameter_rules"]}
        assert "include_thoughts" not in names, model


# Every entry mirrors specs.reasoning_options[type="effort"] in the AiHubMix public
# projection (https://aihubmix.com/model-data/index.json, schema 2.0.0). Where the
# projection's default is not itself listed in `values` it is still a real, accepted
# wire value, so it is folded into the options list.
PROJECTION_REASONING_EFFORT = {
    "coding-glm-5.2": (["none", "minimal", "low", "medium", "high", "xhigh", "max"], "max"),
    "coding-glm-5.3": (["low", "medium", "high", "max"], "medium"),
    "coding-kimi-k3": (["low", "medium", "high", "max"], "medium"),
    "deepseek-v4-flash-0731-fast": (["none", "low", "medium", "high", "max"], "medium"),
    "deepseek-v4-flash-vision-exp": (["none", "low", "medium", "high", "max"], "medium"),
    "deepseek-v4.1-flash": (["none", "low", "medium", "high", "max"], "medium"),
    "glm-5.2-fast-preview": (["none", "minimal", "low", "medium", "high", "xhigh", "max"], "max"),
    "gpt-5.5-pro": (["medium", "high", "xhigh"], "medium"),
    "gpt-5.6-sol-disc": (["none", "low", "medium", "high", "xhigh", "max"], "medium"),
    "gpt-6-astra": (["low", "medium", "high", "xhigh", "max"], "medium"),
    "hy3-preview": (["no_think", "low", "high"], "no_think"),
    "hy4-preview": (["none", "high"], "high"),
    "mercury-2.5-preview": (["instant", "low", "medium", "high"], "medium"),
    "muse-spark-1.1": (["minimal", "low", "medium", "high", "xhigh"], "medium"),
    "muse-spark-1.2": (["minimal", "low", "medium", "high", "xhigh"], "medium"),
    "muse-spark-1.3": (["minimal", "low", "medium", "high", "xhigh"], "medium"),
    "ox-alpha": (["low", "medium", "high", "max"], "medium"),
    "qwen3.8-flash": (["low", "medium", "xhigh"], "medium"),
    "qwen3.8-max-2026-09-02": (["none", "minimal", "low", "medium", "high", "xhigh", "max"], "xhigh"),
}

# specs.context_window / specs.max_output_tokens from the same projection.
PROJECTION_LIMITS = {
    "glm-5.2-fast-preview": (1_000_000, "max_tokens", 131_072),
    "hy3-preview": (256_000, "max_tokens", 128_000),
    "hy4-preview": (1_048_576, "max_tokens", 64_000),
    "qwen3.8-flash": (1_000_000, "max_completion_tokens", 131_072),
    "qwen3.8-max-2026-09-02": (1_000_000, "max_completion_tokens", 131_072),
}


def test_reasoning_effort_matches_public_projection() -> None:
    for model, (options, default) in PROJECTION_REASONING_EFFORT.items():
        rule = _rule(model, "reasoning_effort")
        assert rule["options"] == options, model
        assert rule["default"] == default, model


def test_limits_match_public_projection() -> None:
    for model, (context, rule_name, max_output) in PROJECTION_LIMITS.items():
        assert _schema(model)["model_properties"]["context_size"] == context, model
        assert _rule(model, rule_name)["max"] == max_output, model


def test_inert_knobs_are_not_exposed() -> None:
    # A boolean `thinking` reaches glm-5.2-fast-preview as `"thinking": false`, which the
    # endpoint answers 200 to while still streaming reasoning_content back. The official
    # shape is the object `{"type": "disabled"}`, which Dify parameter_rules cannot express,
    # so the working reasoning_effort=none is the off switch instead.
    rules = {rule["name"] for rule in _schema("glm-5.2-fast-preview")["parameter_rules"]}
    assert "thinking" not in rules
    assert "thinking_budget" not in rules
    # reasoning_mode appears nowhere in the projection for gpt-5.6-sol-disc.
    assert "reasoning_mode" not in {r["name"] for r in _schema("gpt-5.6-sol-disc")["parameter_rules"]}


def test_agnes_thinking_toggle_uses_chat_template_kwargs() -> None:
    # The projection names chat_template_kwargs.enable_thinking as the official toggle;
    # llm.py rewrites a YAML `enable_thinking` into exactly that object.
    for model in ("agnes-2.5-flash", "agnes-3.0-flash"):
        assert _rule(model, "enable_thinking")["type"] == "boolean", model
