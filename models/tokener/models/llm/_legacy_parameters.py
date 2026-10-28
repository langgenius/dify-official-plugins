"""Explicit adapters for known Dify-provider parameter contracts.

This is not a generic passthrough. The caller still runs SDK validation on
``sdk_parameters``, then merges the small, separately validated ``wire_overrides``.
Native Gemini extensions require confirmation of the deployed LiteLLM contract;
an OpenAI-compatible model ID alone does not establish that contract.
"""

import json
import math
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dify_plugin.errors.model import InvokeBadRequestError

CONTRACTS = json.loads(
    (Path(__file__).resolve().parents[2] / "scripts" / "legacy_parameter_contracts.json").read_text(
        encoding="utf-8"
    )
)
TRANSPORT_FIELDS = frozenset(
    {
        "api_key",
        "api_base",
        "base_url",
        "endpoint_url",
        "endpoint_model_name",
        "extra_headers",
        "headers",
        "credentials",
        "model",
        "messages",
        "input",
        "stream",
        "stream_options",
        "tools",
        "functions",
        "user",
        "metadata",
        "extra_body",
        "timeout",
        "max_retries",
        "custom_llm_provider",
        "api_version",
        "litellm_params",
        "drop_params",
        "allowed_openai_params",
        "additional_drop_params",
    }
)
CACHE_FLAGS = frozenset(
    {
        "prompt_caching_tool_definitions",
        "prompt_caching_system_message",
        "prompt_caching_images",
        "prompt_caching_documents",
        "prompt_caching_tool_results",
    }
)
NATIVE_TOOL_FIELDS = {
    "grounding": "googleSearch",
    "url_context": "urlContext",
    "code_execution": "codeExecution",
}


@dataclass(frozen=True)
class LegacyParameterPlan:
    sdk_parameters: dict[str, Any]
    wire_overrides: dict[str, Any] = field(default_factory=dict)
    stream_enabled: bool | None = None
    consumed_parameters: tuple[str, ...] = ()

    def effective_stream(self, requested: bool) -> bool:
        """An enabled toggle permits streaming; it never overrides caller false."""
        return requested and self.stream_enabled is not False


def _reject(name: str, reason: str = "unsupported value") -> None:
    # Deliberately omit parameter values: a mistaken credential must not leak.
    raise InvokeBadRequestError(f"Tokener.ai parameter '{name}': {reason}")


def _boolean(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        _reject(name, "expected a boolean")
    return value


def _number(name: str, value: Any, minimum: float, maximum: float, *, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _reject(name, "expected a number")
    if not math.isfinite(value) or (integer and not isinstance(value, int)):
        _reject(name, "expected a finite integer" if integer else "expected a finite number")
    if not minimum <= value <= maximum:
        _reject(name, "outside the source provider's supported range")
    return value


def _option(name: str, value: Any, options: list[str]) -> str:
    if not isinstance(value, str) or value not in options:
        _reject(name, "outside the source provider's supported options")
    return value


def _gemini_fields(contract: dict) -> set[str]:
    fields = {"max_output_tokens", "include_thoughts", "json_schema", *NATIVE_TOOL_FIELDS}
    if contract.get("sampling"):
        fields.update({"temperature", "top_p"})
    if "thinking_budget_max" in contract:
        fields.update({"thinking_mode", "thinking_budget"})
    if "thinking_levels" in contract:
        fields.add("thinking_level")
    for name in ("media_resolution", "flex_inference", "service_tier"):
        if contract.get(name):
            fields.add(name)
    return fields


def legacy_parameter_names(model: str) -> set[str]:
    """Exact-model compatibility inputs; never expands model identities."""
    names: set[str] = set()
    if model in CONTRACTS["reasoning_effort_options"]:
        names.add("reasoning_effort")
    if model in CONTRACTS["qwen_thinking_models"]:
        names.add("enable_thinking")
    if model in CONTRACTS["local_stream_control_models"]:
        names.add("enable_stream")
    if contract := CONTRACTS["gemini_models"].get(model):
        names |= _gemini_fields(contract)
    if model in CONTRACTS["anthropic_cache_ttl_models"]:
        names |= {"prompt_caching_ttl", "prompt_caching_message_flow", *CACHE_FLAGS}
    return names


def _gemini_json_schema(parameters: dict, overrides: dict, *, has_custom_tools: bool) -> bool:
    """Convert the source's standalone raw schema, not native Tokener selectors.

    Google plugin0.9.12 sets response_mime_type=application/json whenever the
    key exists; only a nonempty value adds response_json_schema. OpenAI-compatible
    chat uses response_format, whose json_schema member needs a name + schema.
    """
    if "json_schema" not in parameters or "response_format" in parameters:
        return False
    if has_custom_tools:
        _reject("json_schema", "structured output with custom tools has no reviewed mapping")
    raw = parameters.pop("json_schema")
    if raw is None or raw == "":
        overrides["response_format"] = "json_object"
        return True
    if not isinstance(raw, str):
        _reject("json_schema", "expected a JSON object encoded as text")

    def reject_constant(_value):
        raise ValueError("non-finite JSON")

    try:
        schema = json.loads(raw, parse_constant=reject_constant)
    except (TypeError, ValueError):
        _reject("json_schema", "expected a valid JSON object")
    if not isinstance(schema, dict):
        _reject("json_schema", "expected a JSON object")
    overrides["response_format"] = "json_schema"
    overrides["json_schema"] = json.dumps(
        {"name": "dify_legacy_schema", "schema": schema}, ensure_ascii=False, allow_nan=False
    )
    return True


def _adapt_gemini(
    parameters: dict,
    overrides: dict,
    contract: dict,
    *,
    native_contract: bool,
    google_openai_contract: bool,
    has_custom_tools: bool,
    defer_schema_tool_conflict: bool,
) -> list[str]:
    consumed: list[str] = []

    def take(name):
        consumed.append(name)
        return parameters.pop(name)

    if "max_output_tokens" in parameters:
        value = _number("max_output_tokens", take("max_output_tokens"), 1, 2**31 - 1, integer=True)
        if "max_tokens" in parameters:
            existing = _number("max_tokens", parameters["max_tokens"], 1, 2**31 - 1, integer=True)
            if existing != value:
                _reject("max_output_tokens", "conflicts with max_tokens")
        parameters["max_tokens"] = value  # SDK enforces the actual target model limit.

    if contract.get("sampling"):
        for name, maximum in (("temperature", 2), ("top_p", 1)):
            if name in parameters:
                overrides[name] = _number(name, take(name), 0, maximum)

    generation_config: dict[str, Any] = {}
    thinking: dict[str, Any] = {}
    if "include_thoughts" in parameters:
        value = _boolean("include_thoughts", take("include_thoughts"))
        if native_contract or google_openai_contract:
            thinking["includeThoughts"] = value
        elif value:
            _reject("include_thoughts", "native Gemini transport contract is not confirmed")
        # False is Gemini's native default; without a native contract consume only this no-op.

    mode = None
    if "thinking_mode" in parameters:
        mode = _boolean("thinking_mode", take("thinking_mode"))
    budget = None
    if "thinking_budget" in parameters:
        budget = _number(
            "thinking_budget",
            take("thinking_budget"),
            0,
            contract["thinking_budget_max"],
            integer=True,
        )
    # Exact Google plugin 0.9.12 tri-state semantics: zero with absent/true mode
    # means dynamic (-1), but false explicitly disables thinking (zero).
    if mode is False:
        budget = 0
    elif mode is True and (budget is None or budget == 0):
        budget = -1
    elif mode is None and budget == 0:
        budget = -1
    if budget is not None:
        if not (native_contract or google_openai_contract):
            _reject("thinking_mode", "native Gemini transport contract is not confirmed")
        thinking["thinkingBudget"] = budget
    if "thinking_level" in parameters:
        value = _option("thinking_level", take("thinking_level"), contract["thinking_levels"])
        if not (native_contract or google_openai_contract):
            _reject("thinking_level", "native Gemini transport contract is not confirmed")
        thinking["thinkingLevel"] = value.lower()
    if thinking:
        generation_config["thinkingConfig"] = thinking

    if "media_resolution" in parameters:
        value = _option(
            "media_resolution", take("media_resolution"), ["Default", "Low", "Medium", "High"]
        )
        if native_contract:
            suffix = "UNSPECIFIED" if value == "Default" else value.upper()
            generation_config["mediaResolution"] = f"MEDIA_RESOLUTION_{suffix}"
        elif value != "Default":
            reason = (
                "not supported by the reviewed Google OpenAI-compatible transport"
                if google_openai_contract
                else "native Gemini transport contract is not confirmed"
            )
            _reject("media_resolution", reason)

    native_tools = []
    enabled = set()
    for name, wire_name in NATIVE_TOOL_FIELDS.items():
        if name in parameters:
            value = _boolean(name, take(name))
            # Source plugin disables native tools whenever custom functions exist.
            if value and not has_custom_tools:
                enabled.add(name)
                native_tools.append({wire_name: {}})
    if {"url_context", "code_execution"} <= enabled:
        _reject("url_context", "cannot be combined with code_execution")
    if native_tools:
        if google_openai_contract:
            _reject(
                "grounding/url_context/code_execution",
                "not supported by the reviewed Google OpenAI-compatible chat transport",
            )
        if not native_contract:
            _reject(
                "grounding/url_context/code_execution",
                "native Gemini transport contract is not confirmed",
            )
        if parameters.get("json_schema"):
            # Source Gemini3 changes endpoint for this combination. Do not claim
            # generateContent/OpenAI wire equivalence without an Interactions adapter.
            _reject(
                "json_schema", "native tools with structured output require an Interactions adapter"
            )
        overrides["tools"] = native_tools

    tier = None
    if "flex_inference" in parameters:
        if _boolean("flex_inference", take("flex_inference")):
            tier = "flex"
    if "service_tier" in parameters:
        supplied_tier = _option(
            "service_tier", take("service_tier"), ["standard", "flex", "priority"]
        )
        tier = tier or supplied_tier  # flex_inference wins in source plugin.
    if tier is not None:
        if google_openai_contract and tier == "standard":
            # Google's OpenAI compatibility documentation explicitly defines an
            # omitted service_tier as standard. Preserve that source default by
            # omission; it does not establish that the REST enum accepts the
            # literal "standard" (nor do we guess a "default" substitution).
            pass
        elif native_contract or google_openai_contract:
            overrides["service_tier"] = tier
        elif tier != "standard":
            _reject("service_tier", "native Gemini transport contract is not confirmed")

    if _gemini_json_schema(
        parameters,
        overrides,
        has_custom_tools=has_custom_tools and not defer_schema_tool_conflict,
    ):
        consumed.append("json_schema")

    if google_openai_contract and thinking:
        snake_keys = {
            "thinkingBudget": "thinking_budget",
            "thinkingLevel": "thinking_level",
            "includeThoughts": "include_thoughts",
        }
        google_thinking = {snake_keys[key]: value for key, value in thinking.items()}
        # Tokener receives raw JSON; LiteLLM's OpenAI adapter passes the outer
        # extra_body as an openai-python argument, which flattens exactly once.
        # Google REST must ultimately receive extra_body.google.thinking_config.
        overrides["extra_body"] = {"extra_body": {"google": {"thinking_config": google_thinking}}}
    elif generation_config:
        # This is LiteLLM's reviewed native Gemini extension, not an arbitrary
        # caller-provided extra_body and not a fake top-level source parameter.
        overrides["extra_body"] = {"generationConfig": generation_config}
    return consumed


def prepare_legacy_parameters(
    model: str,
    parameters: dict[str, Any],
    *,
    declared_parameters: set[str],
    gemini_native_contract: bool = False,
    gemini_google_openai_contract: bool = False,
    has_custom_tools: bool = False,
    defer_schema_tool_conflict: bool = False,
) -> LegacyParameterPlan:
    """Validate known compatibility inputs before the SDK's schema filtering.

    Unknown legacy parameters are rejected for covered models; schema-declared
    native inputs are left to normal SDK validation. No defaults are injected.
    The caller must merge wire_overrides *after* SDK filtering and consume the
    stream toggle locally. Do not pass the plan itself to the transport.
    """
    copied = deepcopy(parameters)
    if gemini_native_contract and gemini_google_openai_contract:
        _reject("Gemini transport", "native and Google OpenAI-compatible contracts are exclusive")
    for name in copied:
        if name in TRANSPORT_FIELDS:
            _reject(name, "transport fields are not model parameters")

    options = CONTRACTS["reasoning_effort_options"].get(model)
    qwen = model in CONTRACTS["qwen_thinking_models"]
    stream_control = model in CONTRACTS["local_stream_control_models"]
    gemini = CONTRACTS["gemini_models"].get(model)
    cache_ttl = model in CONTRACTS["anthropic_cache_ttl_models"]
    if not any((options, qwen, stream_control, gemini, cache_ttl)):
        return LegacyParameterPlan(copied)

    accepted = set(declared_parameters) | {"tool_choice"}
    if model in CONTRACTS["native_sdk_filtered_sampling_models"]:
        # Existing native Tokener behavior intentionally leaves Dify's built-in
        # sampling defaults to the SDK allowlist on these exact reasoning models.
        # Keep that behavior when a legacy stream/effort control is also present;
        # this exception does not add either field to wire_overrides.
        accepted |= {"temperature", "top_p"}
    if options:
        accepted.add("reasoning_effort")
    if qwen:
        accepted.add("enable_thinking")
    if stream_control:
        accepted.add("enable_stream")
    if gemini:
        accepted |= _gemini_fields(gemini)
    if cache_ttl:
        accepted |= {"prompt_caching_ttl", "prompt_caching_message_flow", *CACHE_FLAGS}
    for name in copied:
        if name not in accepted:
            _reject(name, "no reviewed compatibility mapping for this model")

    wire: dict[str, Any] = {}
    consumed: list[str] = []
    stream = None
    if stream_control and "enable_stream" in copied:
        stream = _boolean("enable_stream", copied.pop("enable_stream"))
        consumed.append("enable_stream")
    if qwen and "enable_thinking" in copied:
        wire["enable_thinking"] = _boolean("enable_thinking", copied.pop("enable_thinking"))
        consumed.append("enable_thinking")
    if options and "reasoning_effort" in copied:
        wire["reasoning_effort"] = _option(
            "reasoning_effort", copied.pop("reasoning_effort"), options
        )
        consumed.append("reasoning_effort")
    if gemini:
        consumed += _adapt_gemini(
            copied,
            wire,
            gemini,
            native_contract=gemini_native_contract,
            google_openai_contract=gemini_google_openai_contract,
            has_custom_tools=has_custom_tools,
            defer_schema_tool_conflict=defer_schema_tool_conflict,
        )
    if cache_ttl:
        for name in CACHE_FLAGS:
            if name in copied:
                if _boolean(name, copied.pop(name)):
                    _reject(name, "cache block conversion is not implemented")
                consumed.append(name)
        if "prompt_caching_message_flow" in copied:
            value = _number(
                "prompt_caching_message_flow",
                copied.pop("prompt_caching_message_flow"),
                0,
                2**31 - 1,
                integer=True,
            )
            if value:
                _reject("prompt_caching_message_flow", "cache block conversion is not implemented")
            consumed.append("prompt_caching_message_flow")
        if "prompt_caching_ttl" in copied:
            _option("prompt_caching_ttl", copied.pop("prompt_caching_ttl"), ["5m", "1h"])
            # With every cache flag off, the source attaches no cache_control.
            consumed.append("prompt_caching_ttl")
    return LegacyParameterPlan(copied, wire, stream, tuple(consumed))
