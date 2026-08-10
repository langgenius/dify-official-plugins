from pathlib import Path

import yaml
from dify_plugin.entities.model.message import UserPromptMessage

from models.llm import llm as llm_module
from models.llm.llm import AnthropicLargeLanguageModel


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


def _capture_payload(
    monkeypatch,
    model_parameters: dict,
    model: str = "claude-opus-5",
) -> dict:
    _Anthropic.instances = []
    monkeypatch.setattr(llm_module, "Anthropic", _Anthropic)

    AnthropicLargeLanguageModel()._chat_generate(
        model=model,
        credentials={"anthropic_api_key": "test-key"},
        prompt_messages=[UserPromptMessage(content="Hello")],
        model_parameters=dict(model_parameters),
        stream=True,
    )

    return _Anthropic.instances[0].messages.calls[0]


def test_opus5_schema_defaults_match_anthropic_docs() -> None:
    schema_path = Path(__file__).parents[1] / "models" / "llm" / "claude-opus-5.yaml"
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    rules = {rule["name"]: rule for rule in schema["parameter_rules"]}

    # Thinking is ON by default on Opus 5 (breaking change vs Opus 4.8).
    assert rules["thinking"]["default"] is True
    assert rules["thinking_display"]["default"] == "omitted"
    assert rules["effort"]["default"] == "high"
    # Opus 5 inherits task budgets from Opus 4.8.
    assert "task_budget" in rules
    # Same pricing as Opus 4.8.
    assert schema["pricing"] == {
        "input": "5.00",
        "output": "25.00",
        "unit": "0.000001",
        "currency": "USD",
    }
    assert schema["model_properties"]["context_size"] == 1000000


def test_opus5_omitted_thinking_preserves_api_default(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 1024,
            "temperature": 0,
            "top_p": 0.1,
            "top_k": 1,
        },
    )

    # Thinking is on by default; omitting the field uses the API's adaptive-on default.
    assert "thinking" not in payload
    # Adaptive-thinking models reject non-default sampling params with 400; dropped.
    assert "temperature" not in payload
    assert "top_p" not in payload
    assert "top_k" not in payload
    assert "output_config" not in payload
    assert payload["extra_headers"] == {}


def test_opus5_explicit_true_uses_adaptive_thinking(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 1024,
            "thinking": True,
            "thinking_display": "summarized",
            "effort": "max",
        },
    )

    assert payload["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert payload["output_config"] == {"effort": "max"}


def test_opus5_explicit_false_disables_thinking_at_low_effort(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 1024,
            "thinking": False,
            "effort": "low",
        },
    )

    assert payload["thinking"] == {"type": "disabled"}
    # effort=low is allowed with thinking disabled; no clamp needed.
    assert payload["output_config"] == {"effort": "low"}


def test_opus5_disabled_thinking_clamps_xhigh_effort_to_high(monkeypatch, caplog) -> None:
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 1024,
            "thinking": False,
            "effort": "xhigh",
        },
    )

    # thinking=disabled + effort=xhigh is a 400 on Opus 5; plugin clamps to high.
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["output_config"] == {"effort": "high"}
    assert "clamping effort to 'high'" in caplog.text


def test_opus5_disabled_thinking_clamps_max_effort_to_high(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 1024,
            "thinking": False,
            "effort": "max",
        },
    )

    assert payload["thinking"] == {"type": "disabled"}
    assert payload["output_config"] == {"effort": "high"}


def test_opus5_task_budget_sent_with_beta_header(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 1024,
            "thinking": True,
            "task_budget": 64000,
        },
    )

    assert payload["output_config"]["task_budget"] == {"type": "tokens", "total": 64000}
    assert payload["extra_headers"] == {"anthropic-beta": "task-budgets-2026-03-13"}


def test_opus5_task_budget_below_minimum_silently_ignored(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 1024,
            "thinking": True,
            "task_budget": 10000,
        },
    )

    assert "task_budget" not in payload.get("output_config", {})
    assert payload["extra_headers"] == {}
