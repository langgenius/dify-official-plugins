from pathlib import Path

import yaml


MODEL_DIR = Path(__file__).parents[1] / "models" / "llm"

NEW_MODELS = (
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
    # `max` is dropped: the plugin dispatches gpt-6-astra over chat/completions, and there
    # max costs exactly as many reasoning tokens as medium (6 vs 6 across four runs each)
    # while xhigh escalates to 21-43. On the /responses surface max does work (215-380
    # against 143-184 for xhigh), but that is not the surface this schema drives.
    assert astra_rules["reasoning_effort"]["options"] == ["low", "medium", "high", "xhigh"]
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

    # The object form does switch thinking on ernie-5.1 (429 reasoning tokens enabled,
    # none disabled), but reasoning_effort=none already turns it off just as completely,
    # so the model is not given a second switch for the same thing.
    assert "thinking" not in rules
    assert rules["reasoning_effort"]["options"] == ["none", "low", "medium", "high"]
    # json_schema is silently ignored here - the gateway answers a schema-constrained
    # request in prose - so only json_object is offered.
    assert rules["response_format"]["options"] == ["text", "json_object"]
    assert "json_schema" not in rules


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
    # Six of these schemas were filed under a name that differs from the id `_position.yaml`
    # registers (`deepseek-r1-aihubmix.yaml` declares `model: aihubmix-DeepSeek-R1`), so the
    # pair has to be tracked explicitly - asserting the filename against the registry would
    # pass even if the retired entry were still listed.
    retired = (
        # (schema filename, id registered in _position.yaml)
        ("gpt-4.5-preview", "gpt-4.5-preview"),
        ("gemini-2.0-flash", "gemini-2.0-flash"),
        ("gemini-2.5-flash-preview-04-17", "gemini-2.5-flash-preview-04-17"),
        ("gemini-2.5-flash-preview-04-17-nothink", "gemini-2.5-flash-preview-04-17-nothink"),
        ("deepseek-v3.2-speciale", "deepseek-v3.2-speciale"),
        ("deepseek-r1-aihubmix", "aihubmix-DeepSeek-R1"),
        ("Llama-3-3-70B-Instruct-aihubmix", "aihubmix-Llama-3-3-70B-Instruct"),
        ("deepSeek-V3-0324", "deepseek-ai/DeepSeek-V3-0324"),
        (
            "llama-4-maverick-17b-128e-instruct-fp8",
            "chutesai/Llama-4-Maverick-17B-128E-Instruct-FP8",
        ),
        ("llama-4-scout-17b-16e-instruct", "chutesai/Llama-4-Scout-17B-16E-Instruct"),
        (
            "llama-4-scout-17b-16e-instruct-meta-llama",
            "meta-llama/llama-4-scout-17b-16e-instruct",
        ),
    )
    positions = _positions()
    for filename, model_id in retired:
        assert not (MODEL_DIR / f"{filename}.yaml").exists(), filename
        assert filename not in positions, filename
        assert model_id not in positions, model_id


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
    "deepseek-v4-flash-0731-fast": (["low", "medium", "high", "max"], "medium"),
    "deepseek-v4-flash-vision-exp": (["low", "medium", "high", "max"], "medium"),
    "deepseek-v4.1-flash": (["low", "medium", "high", "max"], "medium"),
    "glm-5.2": (["none", "minimal", "low", "medium", "high", "xhigh", "max"], "max"),
    "glm-5.2-fast-preview": (["none", "minimal", "low", "medium", "high", "xhigh", "max"], "max"),
    "gpt-5.5-pro": (["medium", "high", "xhigh"], "medium"),
    "gpt-5.6-sol-disc": (["none", "low", "medium", "high", "xhigh", "max"], "medium"),
    "gpt-6-astra": (["low", "medium", "high", "xhigh"], "medium"),  # max is inert on chat/completions
    "hy3-preview": (["no_think", "low", "high"], "no_think"),
    "hy4-preview": (["none", "high"], "high"),
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
    # reasoning_effort is inert on mercury-2.5-preview: across six calls no level ever moved
    # the reasoning-token count in the documented direction, and `instant` - the level that
    # should spend the least - spent the most (864 and 872 against 794 for `high`).
    rules = {rule["name"] for rule in _schema("mercury-2.5-preview")["parameter_rules"]}
    assert "reasoning_effort" not in rules
    # The projection lists reasoning_effort for gemini-3.1-flash-lite-nothink, but that enum
    # belongs to the base model. On the -nothink id the gateway accepts even a bogus value and
    # bills zero reasoning tokens for every level, so the knob stays out.
    rules = {rule["name"] for rule in _schema("gemini-3.1-flash-lite-nothink")["parameter_rules"]}
    assert "reasoning_effort" not in rules


def test_agnes_thinking_toggle_uses_chat_template_kwargs() -> None:
    # The projection names chat_template_kwargs.enable_thinking as the official toggle;
    # llm.py rewrites a YAML `enable_thinking` into exactly that object.
    for model in ("agnes-2.5-flash", "agnes-3.0-flash"):
        assert _rule(model, "enable_thinking")["type"] == "boolean", model


# --- routing and thinking-switch plumbing ------------------------------------
# Two defects the public projection exposed in `llm.py` itself.


def _llm_source() -> str:
    return (MODEL_DIR / "llm.py").read_text(encoding="utf-8")


def _normalize_thinking_switch():
    """Lift the pure helper out of llm.py so it can run without dify_plugin."""
    import re
    import textwrap

    source = _llm_source()
    match = re.search(
        r"    @staticmethod\n    def _normalize_thinking_switch.*?\n        return model_parameters\n",
        source,
        re.S,
    )
    assert match, "llm.py no longer defines _normalize_thinking_switch"
    namespace: dict = {}
    exec(textwrap.dedent(match.group(0).replace("    @staticmethod\n", "")), namespace)
    return namespace["_normalize_thinking_switch"]


def test_gpt_5_5_pro_is_routed_to_the_responses_api() -> None:
    # The projection gives gpt-5.5-pro only openai.responses and
    # anthropic.messages — it has no chat-completions surface, unlike gpt-5.5.
    block = _llm_source().split("RESPONSE_SERIES_COMPATIBILITY = (", 1)[1].split(")", 1)[0]
    assert '"gpt-5.5-pro"' in block
    # ... and none of its rules are chat-completions-only, since
    # openai_response.py rejects them outright.
    names = {rule["name"] for rule in _schema("gpt-5.5-pro")["parameter_rules"]}
    assert names.isdisjoint({"temperature", "top_p", "seed", "presence_penalty", "frequency_penalty"})


def test_boolean_thinking_is_sent_as_the_official_object() -> None:
    # A bare boolean `thinking` is not valid on any vendor's chat-completions
    # schema: doubao/kimi/coding-glm/deepseek/ernie answer HTTP 400, glm-5.2
    # ignores it and still bills reasoning tokens. The official field is an
    # object, which parameter_rules cannot express, so llm.py converts it.
    normalize = _normalize_thinking_switch()
    assert normalize({"thinking": False})["thinking"] == {"type": "disabled"}
    assert normalize({"thinking": True})["thinking"] == {"type": "enabled"}
    # Anything that is not a boolean is passed through untouched.
    assert normalize({"thinking": {"type": "disabled"}})["thinking"] == {"type": "disabled"}
    assert normalize({"temperature": 0.5}) == {"temperature": 0.5}
    # Only the OpenAI-compatible branch converts: anthropic.py consumes the
    # boolean itself, so the call must sit next to super()._generate.
    source = _llm_source()
    tail = source.split("# 默认使用父类的生成方法", 1)[1]
    assert "_normalize_thinking_switch(model_parameters)" in tail.split("super()._generate", 1)[0]


def test_gemini_thinking_toggle_uses_the_name_google_py_reads() -> None:
    # google.py's _set_thinking_config reads thinking_mode, not thinking.
    names = {rule["name"] for rule in _schema("gemini-3-pro-preview")["parameter_rules"]}
    assert "thinking_mode" in names
    assert "thinking" not in names
    assert 'thinking_mode = model_parameters.get("thinking_mode", None)' in (
        MODEL_DIR / "google.py"
    ).read_text(encoding="utf-8")


# --- enums taken from domains[].capabilities[].protocols[].fields[] ----------
# specs.reasoning_options only summarises the reasoning knobs. The per-protocol
# fields carry the rest of the enums, each against the protocol the plugin
# actually routes that model through.


def _responses_source() -> str:
    return (MODEL_DIR / "openai_response.py").read_text(encoding="utf-8")


def test_sol_disc_exposes_every_official_responses_reasoning_field() -> None:
    # gpt-5.6-sol-disc goes to /v1/responses, where the projection marks reasoning.mode,
    # reasoning.summary, reasoning.context and text.verbosity official-model-level. The
    # gateway validates all four server side: a bogus value comes back 400 naming the enum.
    expected = {
        "reasoning_mode": ["standard", "pro"],
        "reasoning_summary": ["auto", "concise", "detailed"],
        "reasoning_context": ["auto", "current_turn", "all_turns"],
        "verbosity": ["low", "medium", "high"],
    }
    for name, options in expected.items():
        assert _rule("gpt-5.6-sol-disc", name)["options"] == options, name
    # Each of those names only reaches the wire because openai_response.py translates it.
    source = _responses_source()
    for name in ("reasoning_effort", "reasoning_summary", "reasoning_mode", "reasoning_context"):
        assert f'("{name}", "' in source, name
    assert 'params.pop("verbosity"' in source


def test_deepseek_v4_flash_turns_thinking_off_through_the_official_field() -> None:
    # The projection's effort enum is low/high/max (medium is its default). Thinking is
    # switched by the separate thinking object, not by an invented reasoning_effort=none.
    for model in ("deepseek-v4.1-flash", "deepseek-v4-flash-vision-exp", "deepseek-v4-flash-0731-fast"):
        assert _rule(model, "thinking")["type"] == "boolean", model
        assert "none" not in _rule(model, "reasoning_effort")["options"], model


def test_json_schema_is_offered_only_where_the_gateway_honours_it() -> None:
    # response_format fields narrowed to text/json_object by the projection, confirmed on the
    # gateway: deepseek answers 400 "This response_format type is unavailable now" and the
    # coding-glm ids answer 200 while ignoring the schema outright.
    for model in ("coding-glm-5.2", "coding-glm-5.3", "deepseek-v4.1-flash", "deepseek-v4-flash-vision-exp"):
        assert _rule(model, "response_format")["options"] == ["text", "json_object"], model
        rules = {rule["name"] for rule in _schema(model)["parameter_rules"]}
        assert "json_schema" not in rules, model
        assert "structured-output" not in (_schema(model).get("features") or []), model
    # The same projection narrows glm-5.2 too, but there the gateway really does constrain
    # decoding to the schema, so the knob stays.
    for model in ("glm-5.2", "glm-5.2-fast-preview", "deepseek-v4-flash-0731-fast"):
        assert "json_schema" in _rule(model, "response_format")["options"], model
    # ox-alpha answers a schema-constrained request in prose, exactly like ernie-5.1.
    ox_rules = {rule["name"] for rule in _schema("ox-alpha")["parameter_rules"]}
    assert "json_schema" not in ox_rules
    assert _rule("ox-alpha", "response_format")["options"] == ["text", "json_object"]
    # mai-thinking-1 rejects every structured format with 400 "Structured `response_format`
    # is not enabled for model", so it gets no response_format knob at all.
    mai = _schema("mai-thinking-1")
    mai_rules = {rule["name"] for rule in mai["parameter_rules"]}
    assert "json_schema" not in mai_rules
    assert "response_format" not in mai_rules
    assert "structured-output" not in (mai.get("features") or [])


def test_structured_output_flag_follows_the_json_schema_rule() -> None:
    # Dify reads capability from the `structured-output` feature flag, not from the
    # response_format options, so a schema that offers `json_schema` while omitting the flag
    # reports structured output as unsupported. Every model this branch touches keeps the two
    # in step. Live-checked against the gateway with a strict schema and a prompt that does not
    # itself ask for JSON, so JSON coming back proves the schema was enforced; muse-spark-1.x
    # (403, key-level restriction) and hy3-preview (502 upstream) could not be reached and
    # follow the projection, the same source their json_schema rule comes from.
    touched_with_json_schema = (
        "agnes-2.5-flash",
        "agnes-2.5-pro",
        "agnes-2.5-pro-alpha",
        "agnes-3.0-flash",
        "deepseek-v4-flash-0731-fast",
        "gemini-3-pro-preview",
        "glm-5.2",
        "glm-5.2-fast-preview",
        "gpt-5.5-pro",
        "gpt-5.6-sol-disc",
        "hy3-preview",
        "hy4-preview",
        "longcat-2.0",
        "mercury-2.5-preview",
        "muse-spark-1.1",
        "muse-spark-1.2",
        "muse-spark-1.3",
    )
    for model in touched_with_json_schema:
        schema = _schema(model)
        assert "json_schema" in _rule(model, "response_format")["options"], model
        assert "structured-output" in (schema.get("features") or []), model


def test_glm_fast_preview_exposes_the_verified_thinking_switch() -> None:
    # Sent as the official object by llm.py, the switch really does stop thinking on
    # glm-5.2-fast-preview (333 reasoning tokens enabled, none disabled), and the budget
    # caps it exactly - a budget of 64 spends 64 reasoning tokens.
    assert _rule("glm-5.2-fast-preview", "thinking")["type"] == "boolean"
    assert _rule("glm-5.2-fast-preview", "thinking_budget")["type"] == "int"
    assert _rule("glm-5.2", "thinking_budget")["type"] == "int"
