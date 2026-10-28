from pathlib import Path

import pytest
import yaml
from dify_plugin.entities.model.message import UserPromptMessage

from models.llm import llm as llm_module
from models.llm.llm import AnthropicLargeLanguageModel, PromptCachingHandler

MODEL = "claude-sonnet-5-5"
MODEL_DIR = Path(__file__).parents[1] / "models" / "llm"


class _Messages:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return object()


class _Anthropic:
    instances: list["_Anthropic"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.messages = _Messages()
        self.instances.append(self)


def _capture_payload(monkeypatch, model_parameters: dict) -> dict:
    _Anthropic.instances = []
    monkeypatch.setattr(llm_module, "Anthropic", _Anthropic)

    AnthropicLargeLanguageModel()._chat_generate(
        model=MODEL,
        credentials={"anthropic_api_key": "test-key"},
        prompt_messages=[UserPromptMessage(content="Hello")],
        model_parameters=dict(model_parameters),
        stream=True,
    )

    return _Anthropic.instances[0].messages.calls[0]


def test_sonnet5_5_schema_matches_anthropic_docs() -> None:
    schema = yaml.safe_load((MODEL_DIR / f"{MODEL}.yaml").read_text(encoding="utf-8"))
    rules = {rule["name"]: rule for rule in schema["parameter_rules"]}

    assert schema["model"] == MODEL
    assert MODEL in yaml.safe_load((MODEL_DIR / "_position.yaml").read_text())
    assert schema["model_properties"]["context_size"] == 1_000_000
    assert "structured-output" in schema["features"]
    assert {"response_format", "json_schema"} <= rules.keys()
    assert rules["max_tokens"]["max"] == 128_000
    # Adaptive thinking is on by default and can be turned off via between_tools.
    assert rules["thinking"]["default"] is True
    assert rules["thinking_display"]["default"] == "omitted"
    # Default effort is high on the Claude API.
    assert rules["effort"]["default"] == "high"
    assert rules["effort"]["options"] == ["low", "medium", "high", "xhigh", "max"]
    # task_budget is not documented for Sonnet 5.5 and the plugin gate excludes it.
    assert "task_budget" not in rules
    # budget_tokens and non-default sampling parameters are rejected with 400.
    assert not {"thinking_budget", "temperature", "top_p", "top_k"} & rules.keys()
    # Flat $2 / $10 per MTok.
    assert schema["pricing"] == {
        "input": "2.00",
        "output": "10.00",
        "unit": "0.000001",
        "currency": "USD",
    }


def test_sonnet5_5_omitted_thinking_preserves_api_default(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {"max_tokens": 1024, "temperature": 0, "top_p": 0.1, "top_k": 1},
    )

    assert "thinking" not in payload
    assert not {"temperature", "top_p", "top_k", "extra_body"} & payload.keys()


def test_sonnet5_5_explicit_true_uses_adaptive_thinking(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {"max_tokens": 1024, "thinking": True, "effort": "high", "thinking_budget": 2048},
    )

    assert payload["thinking"] == {"type": "adaptive", "display": "omitted"}
    assert payload["output_config"] == {"effort": "high"}


def test_sonnet5_5_explicit_false_uses_between_tools(monkeypatch) -> None:
    # thinking.type=disabled returns a 400 on Sonnet 5.5; the off switch is
    # between_tools, which accepts no other field (display/budget_tokens -> 400).
    payload = _capture_payload(
        monkeypatch, {"max_tokens": 1024, "thinking": False, "effort": "low"}
    )

    assert payload["thinking"] == {"type": "between_tools"}
    assert payload["output_config"] == {"effort": "low"}


@pytest.mark.parametrize("effort", ["xhigh", "max"])
def test_sonnet5_5_between_tools_clamps_effort_to_high(monkeypatch, effort) -> None:
    # between_tools is accepted only at effort low/medium/high.
    payload = _capture_payload(
        monkeypatch, {"max_tokens": 1024, "thinking": False, "effort": effort}
    )

    assert payload["thinking"] == {"type": "between_tools"}
    assert payload["output_config"] == {"effort": "high"}


def test_sonnet5_5_adaptive_thinking_keeps_xhigh_effort(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch, {"max_tokens": 1024, "thinking": True, "effort": "xhigh"}
    )

    assert payload["thinking"] == {"type": "adaptive", "display": "omitted"}
    assert payload["output_config"] == {"effort": "xhigh"}


def test_sonnet5_5_cache_read_multiplier_is_half_default() -> None:
    # Cache reads are $0.10 / MTok against $2.00 input: 0.05, half the default 0.1.
    assert AnthropicLargeLanguageModel._cache_read_multiplier(MODEL) == 0.05
    assert PromptCachingHandler.CACHE_READ_MULTIPLIER == 0.1


def test_sonnet5_5_custom_model_schema_defaults_effort_to_high() -> None:
    custom_schema = AnthropicLargeLanguageModel().get_customizable_model_schema(MODEL, {})
    rules = {rule.name: rule for rule in custom_schema.parameter_rules}

    assert rules["effort"].default == "high"
    assert not {"thinking_budget", "temperature", "top_p", "top_k"} & rules.keys()
