import ast
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import UserPromptMessage
from dify_plugin.errors.model import InvokeBadRequestError

from models.llm._legacy_parameters import (
    CONTRACTS,
    TRANSPORT_FIELDS,
    prepare_legacy_parameters,
)
from models.llm.llm import TokenerLargeLanguageModel

DECLARED = {"max_tokens", "temperature", "top_p", "response_format", "json_schema"}


def prepare(model, parameters, **kwargs):
    return prepare_legacy_parameters(model, parameters, declared_parameters=DECLARED, **kwargs)


@pytest.mark.parametrize("model", CONTRACTS["qwen_thinking_models"])
@pytest.mark.parametrize("value", [False, True])
def test_qwen_thinking_boolean_preserves_false_without_extra_body(model, value):
    original = {"max_tokens": 256, "enable_thinking": value}
    plan = prepare(model, original)
    assert plan.sdk_parameters == {"max_tokens": 256}
    assert plan.wire_overrides == {"enable_thinking": value}
    assert original == {"max_tokens": 256, "enable_thinking": value}


@pytest.mark.parametrize("value", [0, 1, "false", None, [], {}])
def test_boolean_does_not_accept_truthy_or_zero_coercions(value):
    with pytest.raises(InvokeBadRequestError):
        prepare("qwen3.5-plus", {"enable_thinking": value})


@pytest.mark.parametrize("model", CONTRACTS["reasoning_effort_options"])
def test_each_exact_reasoning_model_uses_its_source_options(model):
    for value in CONTRACTS["reasoning_effort_options"][model]:
        plan = prepare(model, {"reasoning_effort": value})
        assert plan.wire_overrides == {"reasoning_effort": value}
        assert "reasoning_effort" not in plan.sdk_parameters
    with pytest.raises(InvokeBadRequestError):
        prepare(model, {"reasoning_effort": "ultra"})


@pytest.mark.parametrize("model", CONTRACTS["local_stream_control_models"])
@pytest.mark.parametrize("requested", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
def test_stream_control_never_becomes_a_wire_model_parameter(model, requested, enabled):
    plan = prepare(model, {"enable_stream": enabled, "max_tokens": 256})
    assert plan.effective_stream(requested) is (requested and enabled)
    assert plan.sdk_parameters == {"max_tokens": 256}
    assert "enable_stream" not in plan.wire_overrides


def test_absent_controls_do_not_change_native_defaults():
    for model in ("qwen3.5-plus", "gpt-5", "gemini-3.5-flash", "claude-opus-4-7"):
        plan = prepare(model, {"max_tokens": 256})
        assert plan.sdk_parameters == {"max_tokens": 256}
        assert plan.wire_overrides == {}
        assert plan.stream_enabled is None


@pytest.mark.parametrize("model", CONTRACTS["gemini_models"])
def test_gemini_source_cap_is_a_real_alias_without_diagnostic_cap(model):
    plan = prepare(model, {"max_output_tokens": 256})
    assert plan.sdk_parameters == {"max_tokens": 256}
    assert plan.wire_overrides == {}
    assert prepare(model, {"max_output_tokens": 256, "max_tokens": 256}).sdk_parameters == {
        "max_tokens": 256
    }
    with pytest.raises(InvokeBadRequestError, match="conflicts"):
        prepare(model, {"max_output_tokens": 256, "max_tokens": 512})


@pytest.mark.parametrize("value", [True, 0, -1, 1.5, float("inf"), float("nan"), "256"])
def test_gemini_cap_rejects_invalid_types_and_ranges(value):
    with pytest.raises(InvokeBadRequestError):
        prepare("gemini-2.5-flash", {"max_output_tokens": value})


def test_alias_does_not_hide_invalid_original_max_tokens():
    with pytest.raises(InvokeBadRequestError):
        prepare("gemini-2.5-flash", {"max_output_tokens": 1, "max_tokens": True})


def test_gemini_zero_sampling_is_not_lost_to_target_reasoning_schema_filter():
    plan = prepare("gemini-3-flash-preview", {"temperature": 0, "top_p": 0})
    assert plan.wire_overrides == {"temperature": 0, "top_p": 0}
    assert plan.sdk_parameters == {}


@pytest.mark.parametrize(
    "name,value",
    [("temperature", True), ("temperature", -1), ("top_p", 2), ("top_p", float("nan"))],
)
def test_gemini_sampling_range_is_source_checked(name, value):
    with pytest.raises(InvokeBadRequestError):
        prepare("gemini-3-flash-preview", {name: value})


def _source_thinking_function():
    """Execute only the actual checked-in Gemini pure config method, not imports.

    This method is unchanged from pinned Gemini0.9.12. AST isolation makes the
    differential test independent of Google's SDK, credentials and networking.
    The public plugin package can run the other tests without sibling plugins.
    """
    source = Path(__file__).resolve().parents[3] / "models/gemini/models/llm/llm.py"
    if not source.is_file():
        pytest.skip("sibling Gemini source is required for this differential test")
    tree = ast.parse(source.read_text())
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "GoogleLargeLanguageModel"
    )
    method = deepcopy(
        next(
            node
            for node in cls.body
            if isinstance(node, ast.FunctionDef) and node.name == "_set_thinking_config"
        )
    )
    method.decorator_list = []
    module = ast.Module(
        body=[
            ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
            method,
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)

    class ThinkingLevel(str):
        pass

    for name in ("MINIMAL", "LOW", "MEDIUM", "HIGH", "THINKING_LEVEL_UNSPECIFIED"):
        setattr(ThinkingLevel, name, ThinkingLevel(name.lower()))
    scope = {
        "IMAGE_GENERATION_MODELS": [],
        "types": SimpleNamespace(
            ThinkingLevel=ThinkingLevel,
            ThinkingConfig=lambda **kwargs: kwargs,
        ),
    }
    exec(compile(module, str(source), "exec"), scope)
    return scope["_set_thinking_config"]


@pytest.mark.parametrize("mode", [None, False, True])
@pytest.mark.parametrize("budget", [None, 0, 1, 8000, 24576])
@pytest.mark.parametrize("include", [None, False, True])
@pytest.mark.parametrize("transport", ["native", "google_openai"])
def test_gemini_thinking_tri_state_matches_actual_source_method(mode, budget, include, transport):
    params = {}
    if mode is not None:
        params["thinking_mode"] = mode
    if budget is not None:
        params["thinking_budget"] = budget
    if include is not None:
        params["include_thoughts"] = include
    reference = SimpleNamespace()
    _source_thinking_function()(
        config=reference, model_parameters=params, model_name="gemini-2.5-flash"
    )
    expected = {
        key: value
        for key, value in {
            "thinkingBudget": reference.thinking_config["thinking_budget"],
            "includeThoughts": reference.thinking_config["include_thoughts"],
        }.items()
        if value is not None
    }
    plan = prepare("gemini-2.5-flash", params, **{f"gemini_{transport}_contract": True})
    if transport == "native":
        actual = (
            plan.wire_overrides.get("extra_body", {})
            .get("generationConfig", {})
            .get("thinkingConfig", {})
        )
    else:
        actual = (
            plan.wire_overrides.get("extra_body", {})
            .get("extra_body", {})
            .get("google", {})
            .get("thinking_config", {})
        )
        expected = {
            "thinking_budget" if key == "thinkingBudget" else "include_thoughts": value
            for key, value in expected.items()
        }
    assert actual == expected
    assert not any(name in plan.sdk_parameters for name in params)


@pytest.mark.parametrize("model,contract", CONTRACTS["gemini_models"].items())
def test_gemini_levels_use_exact_source_options_and_independent_thought_control(model, contract):
    for level in contract.get("thinking_levels", []):
        plan = prepare(
            model, {"thinking_level": level, "include_thoughts": False}, gemini_native_contract=True
        )
        assert plan.wire_overrides == {
            "extra_body": {
                "generationConfig": {
                    "thinkingConfig": {"thinkingLevel": level.lower(), "includeThoughts": False},
                }
            }
        }
    if contract.get("thinking_levels"):
        with pytest.raises(InvokeBadRequestError):
            prepare(model, {"thinking_level": "none"}, gemini_native_contract=True)


def test_gemini_native_transport_is_an_explicit_gate_not_model_name_guessing():
    for params in (
        {"thinking_mode": False},
        {"thinking_level": "Low"},
        {"grounding": True},
        {"include_thoughts": True},
        {"media_resolution": "High"},
        {"service_tier": "flex"},
    ):
        model = "gemini-2.5-flash" if "thinking_mode" in params else "gemini-3.1-flash-lite"
        with pytest.raises(InvokeBadRequestError, match="not confirmed"):
            prepare(model, params)


def test_gemini_neutral_controls_are_consumed_without_fake_wire_fields():
    params = {
        "grounding": False,
        "url_context": False,
        "code_execution": False,
        "include_thoughts": False,
        "media_resolution": "Default",
        "service_tier": "standard",
    }
    plan = prepare("gemini-3.1-flash-lite", params)
    assert plan.sdk_parameters == plan.wire_overrides == {}
    assert set(plan.consumed_parameters) == set(params)
    assert prepare("gemini-2.5-flash", {"flex_inference": False}).wire_overrides == {}


def test_gemini_two_transport_contracts_cannot_be_mixed():
    with pytest.raises(InvokeBadRequestError, match="exclusive"):
        prepare(
            "gemini-3-flash-preview",
            {},
            gemini_native_contract=True,
            gemini_google_openai_contract=True,
        )


@pytest.mark.parametrize(
    "params",
    [
        {"media_resolution": "High"},
        {"grounding": True},
        {"url_context": True},
        {"code_execution": True},
    ],
)
def test_google_openai_does_not_claim_native_features_without_contract(params):
    with pytest.raises(InvokeBadRequestError, match="not supported"):
        prepare("gemini-3-flash-preview", params, gemini_google_openai_contract=True)


def test_native_tools_follow_actual_source_custom_tool_precedence():
    params = {"grounding": True, "url_context": True, "code_execution": True}
    plan = prepare("gemini-3.5-flash", params, has_custom_tools=True)
    assert plan.sdk_parameters == plan.wire_overrides == {}
    with pytest.raises(InvokeBadRequestError, match="cannot be combined"):
        prepare("gemini-3.5-flash", params, gemini_native_contract=True)
    plan = prepare(
        "gemini-3.5-flash", {"grounding": True, "url_context": True}, gemini_native_contract=True
    )
    assert plan.wire_overrides["tools"] == [{"googleSearch": {}}, {"urlContext": {}}]


def test_native_tools_plus_json_schema_do_not_pretend_interactions_support():
    with pytest.raises(InvokeBadRequestError, match="Interactions"):
        prepare(
            "gemini-3.5-flash",
            {"grounding": True, "json_schema": '{"type":"object"}'},
            gemini_native_contract=True,
        )


@pytest.mark.parametrize("tier", ["standard", "flex", "priority"])
def test_service_tier_and_media_resolution_use_real_native_wire(tier):
    plan = prepare(
        "gemini-3.1-flash-lite",
        {"service_tier": tier, "media_resolution": "High"},
        gemini_native_contract=True,
    )
    assert plan.wire_overrides == {
        "service_tier": tier,
        "extra_body": {
            "generationConfig": {"mediaResolution": "MEDIA_RESOLUTION_HIGH"},
        },
    }


@pytest.mark.parametrize("ttl", ["5m", "1h"])
def test_anthropic_ttl_without_cache_flags_is_a_source_noop(ttl):
    plan = prepare(
        "claude-opus-4-7",
        {
            "prompt_caching_ttl": ttl,
            "prompt_caching_system_message": False,
            "prompt_caching_message_flow": 0,
        },
    )
    assert plan.sdk_parameters == plan.wire_overrides == {}


@pytest.mark.parametrize(
    "params",
    [
        {"prompt_caching_ttl": "10m"},
        {"prompt_caching_images": True},
        {"prompt_caching_message_flow": 1},
    ],
)
def test_anthropic_active_cache_is_explicitly_rejected_until_block_adapter_exists(params):
    with pytest.raises(InvokeBadRequestError):
        prepare("claude-opus-4-7", params)


@pytest.mark.parametrize("name", sorted(TRANSPORT_FIELDS))
def test_no_transport_fields_or_credentials_can_escape_as_model_parameters(name):
    with pytest.raises(InvokeBadRequestError) as raised:
        prepare("qwen3.5-plus", {name: "DO_NOT_EXPOSE_SECRET_VALUE"})
    assert "DO_NOT_EXPOSE_SECRET_VALUE" not in str(raised.value)


def test_unknown_parameter_is_not_blindly_passthrough_and_models_are_exact():
    with pytest.raises(InvokeBadRequestError, match="no reviewed"):
        prepare("gpt-5", {"unknown_reasoning": True})
    # No regex matching or fictitious aliases extend this compatibility contract.
    plan = prepare("prefix/gpt-5", {"max_tokens": 256, "enable_thinking": False})
    assert plan.wire_overrides == {}
    assert plan.sdk_parameters == {"max_tokens": 256, "enable_thinking": False}


class BoundaryReached(Exception):
    pass


@pytest.mark.parametrize(
    "model,params,native,expected",
    [
        (
            "qwen3.5-plus",
            {"enable_thinking": False, "max_tokens": 256},
            False,
            {"enable_thinking": False, "max_tokens": 256},
        ),
        (
            "gpt-5",
            {"reasoning_effort": "minimal", "enable_stream": False, "max_tokens": 256},
            False,
            {"reasoning_effort": "minimal", "max_tokens": 256},
        ),
        (
            "gemini-3-flash-preview",
            {
                "max_output_tokens": 256,
                "temperature": 0,
                "include_thoughts": False,
                "thinking_level": "Minimal",
            },
            True,
            {
                "max_tokens": 256,
                "temperature": 0,
                "extra_body": {
                    "generationConfig": {
                        "thinkingConfig": {"includeThoughts": False, "thinkingLevel": "minimal"}
                    }
                },
            },
        ),
    ],
)
def test_plan_survives_real_sdk_filter_to_mocked_http_boundary(model, params, native, expected):
    schema = AIModelEntity.model_validate(
        yaml.safe_load(Path(f"models/llm/{model}.yaml").read_text())
    )
    instance = TokenerLargeLanguageModel(model_schemas=[schema])
    credentials = {"api_key": "OFFLINE_TEST_ONLY"}
    rules = instance.get_parameter_rules(model, credentials)
    plan = prepare_legacy_parameters(
        model,
        params,
        declared_parameters={rule.name for rule in rules},
        gemini_native_contract=native,
    )
    filtered = OAICompatLargeLanguageModel._validate_and_filter_model_parameters(
        instance, model, plan.sdk_parameters, credentials
    )
    wire = {**filtered, **plan.wire_overrides}
    with (
        patch("requests.post", side_effect=BoundaryReached) as post,
        pytest.raises(BoundaryReached),
    ):
        OAICompatLargeLanguageModel._invoke(
            instance,
            model,
            instance._model_credentials(model, credentials),
            [UserPromptMessage(content="offline")],
            wire,
            stream=plan.effective_stream(True),
        )
    post.assert_called_once()
    body = json.loads(post.call_args.kwargs["data"])
    for key, value in expected.items():
        assert body[key] == value
    assert "enable_stream" not in body
    assert "max_output_tokens" not in body
    assert body["stream"] is plan.effective_stream(True)
