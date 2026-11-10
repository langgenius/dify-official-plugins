from pathlib import Path

import pytest
import yaml
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    SystemPromptMessage,
    UserPromptMessage,
)

from models.llm import llm as llm_module
from models.llm.llm import AnthropicLargeLanguageModel

MODEL = "claude-haiku-5-5"
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


def test_haiku5_5_schema_matches_anthropic_docs() -> None:
    schema = yaml.safe_load((MODEL_DIR / f"{MODEL}.yaml").read_text(encoding="utf-8"))
    rules = {rule["name"]: rule for rule in schema["parameter_rules"]}

    assert schema["model"] == MODEL
    assert MODEL in yaml.safe_load((MODEL_DIR / "_position.yaml").read_text())
    assert schema["model_properties"]["context_size"] == 1_000_000
    assert "structured-output" in schema["features"]
    assert {"response_format", "json_schema"} <= rules.keys()
    assert rules["max_tokens"]["max"] == 128_000
    # Thinking is adaptive and on by default, and can be turned off (as on Opus 5).
    assert rules["thinking"]["default"] is True
    assert rules["thinking_display"]["default"] == "omitted"
    # Default effort is medium (not high, as on Opus 5).
    assert rules["effort"]["default"] == "medium"
    assert rules["effort"]["options"] == ["low", "medium", "high", "xhigh", "max"]
    assert "task_budget" in rules
    # budget_tokens and non-default sampling parameters are rejected with 400.
    assert not {"thinking_budget", "temperature", "top_p", "top_k"} & rules.keys()
    # Rates for prompts up to 100K tokens.
    assert schema["pricing"] == {
        "input": "0.10",
        "output": "0.50",
        "unit": "0.000001",
        "currency": "USD",
    }


def test_haiku5_5_omitted_thinking_preserves_api_default(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {"max_tokens": 1024, "temperature": 0, "top_p": 0.1, "top_k": 1},
    )

    assert "thinking" not in payload
    assert not {"temperature", "top_p", "top_k", "extra_body"} & payload.keys()


def test_haiku5_5_explicit_true_uses_adaptive_thinking(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {"max_tokens": 1024, "thinking": True, "effort": "medium", "thinking_budget": 2048},
    )

    assert payload["thinking"] == {"type": "adaptive", "display": "omitted"}
    assert payload["output_config"] == {"effort": "medium"}


def test_haiku5_5_explicit_false_disables_thinking(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch, {"max_tokens": 1024, "thinking": False, "effort": "low"}
    )

    assert payload["thinking"] == {"type": "disabled"}
    assert payload["output_config"] == {"effort": "low"}


@pytest.mark.parametrize("effort", ["xhigh", "max"])
def test_haiku5_5_disabled_thinking_clamps_effort_to_high(monkeypatch, effort) -> None:
    payload = _capture_payload(
        monkeypatch, {"max_tokens": 1024, "thinking": False, "effort": effort}
    )

    # thinking=disabled is accepted only at effort high or below.
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["output_config"] == {"effort": "high"}


def test_haiku5_5_task_budget_and_structured_output(monkeypatch) -> None:
    json_schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 1024,
            "thinking": True,
            "effort": "low",
            "task_budget": 64_000,
            "json_schema": json_schema,
        },
    )

    assert payload["output_config"] == {
        "effort": "low",
        "task_budget": {"type": "tokens", "total": 64_000},
        "format": {"type": "json_schema", "schema": json_schema},
    }
    assert payload["extra_headers"] == {"anthropic-beta": "task-budgets-2026-03-13"}


def test_haiku5_5_json_mode_without_schema_sends_no_prefill() -> None:
    prompt_messages = [
        SystemPromptMessage(content="original system"),
        UserPromptMessage(content="hi"),
    ]

    AnthropicLargeLanguageModel()._transform_chat_json_prompts(
        model=MODEL,
        credentials={"anthropic_api_key": "test-key"},
        prompt_messages=prompt_messages,
        model_parameters={},
        response_format="JSON",
    )

    # Assistant prefill is rejected with 400; the conversation must end on the user turn.
    assert not isinstance(prompt_messages[-1], AssistantPromptMessage)
    assert "original system" in str(prompt_messages[0].content)


def test_haiku5_5_custom_model_schema_defaults_effort_to_medium() -> None:
    custom_schema = AnthropicLargeLanguageModel().get_customizable_model_schema(MODEL, {})
    rules = {rule.name: rule for rule in custom_schema.parameter_rules}

    assert rules["effort"].default == "medium"
    assert not {"thinking_budget", "temperature", "top_p", "top_k"} & rules.keys()
