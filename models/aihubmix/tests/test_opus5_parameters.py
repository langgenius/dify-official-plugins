import json
from pathlib import Path
from typing import ClassVar

import pytest
import yaml
from dify_plugin.entities.model.message import UserPromptMessage

from models.llm import anthropic as anthropic_module
from models.llm.anthropic import AnthropicLargeLanguageModel


class _Messages:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return object()


class _Anthropic:
    instances: ClassVar[list["_Anthropic"]] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.messages = _Messages()
        self.instances.append(self)


def _capture_payload(monkeypatch, model_parameters: dict) -> dict:
    _Anthropic.instances = []
    monkeypatch.setattr(anthropic_module, "Anthropic", _Anthropic)

    AnthropicLargeLanguageModel()._chat_generate(
        model="claude-opus-5",
        credentials={"api_key": "test-key"},
        prompt_messages=[UserPromptMessage(content="Hello")],
        model_parameters=dict(model_parameters),
        stream=True,
    )

    return _Anthropic.instances[0].messages.calls[0]


def test_opus5_schema_matches_aihubmix_facts() -> None:
    schema_path = Path(__file__).parents[1] / "models" / "llm" / "claude-opus-5.yaml"
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))

    assert schema["model_properties"]["context_size"] == 1_000_000
    assert "structured-output" in schema["features"]
    assert schema["pricing"] == {
        "input": "5.00",
        "output": "25.00",
        "unit": "0.000001",
        "currency": "USD",
    }


@pytest.mark.parametrize("effort", ["xhigh", "max"])
def test_opus5_disabled_thinking_clamps_high_effort(monkeypatch, effort: str) -> None:
    payload = _capture_payload(
        monkeypatch,
        {"max_tokens": 16, "thinking": False, "effort": effort},
    )

    assert payload["thinking"] == {"type": "disabled"}
    assert payload["output_config"] == {"effort": "high"}


def test_opus5_maps_json_schema_to_output_config(monkeypatch) -> None:
    schema = {
        "name": "smoke",
        "schema": {
            "type": "object",
            "properties": {"ok": {"type": "string"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
    }
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 16,
            "thinking": True,
            "effort": "high",
            "response_format": "json_schema",
            "json_schema": json.dumps(schema),
        },
    )

    assert payload["output_config"] == {
        "effort": "high",
        "format": {"type": "json_schema", "schema": schema["schema"]},
    }
    assert "response_format" not in payload
    assert "json_schema" not in payload


def test_opus5_rejects_empty_json_schema(monkeypatch) -> None:
    with pytest.raises(ValueError, match="json_schema is required"):
        _capture_payload(
            monkeypatch,
            {
                "max_tokens": 16,
                "thinking": True,
                "response_format": "json_schema",
                "json_schema": "",
            },
        )
