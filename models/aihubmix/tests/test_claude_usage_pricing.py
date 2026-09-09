from decimal import Decimal
from pathlib import Path

import yaml
from anthropic.types import Message, TextBlock, Usage
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import UserPromptMessage

from models.llm import anthropic as anthropic_module
from models.llm.llm import AihubmixLargeLanguageModel

MODEL = "claude-opus-5"
SCHEMA_PATH = Path(__file__).parents[1] / "models" / "llm" / f"{MODEL}.yaml"


class _Messages:
    def create(self, **kwargs):
        return Message(
            id="msg_fake",
            type="message",
            role="assistant",
            model=MODEL,
            content=[TextBlock(type="text", text="hi")],
            stop_reason="end_turn",
            stop_sequence=None,
            usage=Usage(input_tokens=1000, output_tokens=100),
        )


class _Anthropic:
    def __init__(self, **kwargs) -> None:
        self.messages = _Messages()


def _load_schemas() -> list[AIModelEntity]:
    return [AIModelEntity.model_validate(yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8")))]


def test_claude_usage_price_follows_yaml_pricing(monkeypatch) -> None:
    monkeypatch.setattr(anthropic_module, "Anthropic", _Anthropic)

    schemas = _load_schemas()
    pricing = schemas[0].pricing
    assert pricing is not None
    expected_total = (Decimal(1000) * pricing.input + Decimal(100) * pricing.output) * pricing.unit

    llm = AihubmixLargeLanguageModel(schemas)
    with llm.timing_context():
        result = llm._invoke(
            model=MODEL,
            credentials={"api_key": "fake-key-for-test", "api_url": "https://example.invalid"},
            prompt_messages=[UserPromptMessage(content="Hello")],
            model_parameters={"max_tokens": 64, "thinking": False, "effort": "high"},
            stream=False,
        )

    assert result.usage.prompt_tokens == 1000
    assert result.usage.completion_tokens == 100
    assert result.usage.total_price == expected_total
