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
    model: str = "claude-sonnet-5",
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


def test_sonnet5_schema_defaults_match_anthropic_docs() -> None:
    schema_path = Path(__file__).parents[1] / "models" / "llm" / "claude-sonnet-5.yaml"
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    rules = {rule["name"]: rule for rule in schema["parameter_rules"]}

    assert rules["thinking"]["default"] is True
    assert rules["thinking_display"]["default"] == "omitted"
    assert rules["effort"]["default"] == "high"
    assert "task_budget" not in rules


def test_sonnet5_omitted_thinking_preserves_api_default(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 1024,
            "temperature": 0,
            "top_p": 0.1,
            "top_k": 1,
            "task_budget": 64000,
        },
    )

    assert "thinking" not in payload
    assert "temperature" not in payload
    assert "top_p" not in payload
    assert "top_k" not in payload
    assert "output_config" not in payload
    assert payload["extra_headers"] == {}


def test_sonnet5_explicit_false_disables_thinking_without_display(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 1024,
            "thinking": False,
            "thinking_display": "summarized",
            "effort": "low",
        },
    )

    assert payload["thinking"] == {"type": "disabled"}
    assert payload["output_config"] == {"effort": "low"}


def test_sonnet5_explicit_true_uses_adaptive_thinking(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 1024,
            "thinking": True,
            "thinking_display": "summarized",
            "effort": "xhigh",
        },
    )

    assert payload["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert payload["output_config"] == {"effort": "xhigh"}


def test_sonnet5_adaptive_thinking_defaults_display_to_omitted(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 1024,
            "thinking": True,
        },
    )

    assert payload["thinking"] == {"type": "adaptive", "display": "omitted"}


def test_task_budget_still_sent_for_supported_adaptive_models(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 1024,
            "thinking": True,
            "task_budget": 64000,
        },
        model="claude-opus-4-8",
    )

    assert payload["output_config"]["task_budget"] == {"type": "tokens", "total": 64000}
    assert payload["extra_headers"] == {"anthropic-beta": "task-budgets-2026-03-13"}
