import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dify_plugin.entities.model import AIModelEntity, ModelFeature
from dify_plugin.entities.model.message import UserPromptMessage

from models.llm.llm import TongyiLargeLanguageModel


def _model() -> TongyiLargeLanguageModel:
    model = TongyiLargeLanguageModel(model_schemas=MagicMock())
    model.get_model_mode = MagicMock(return_value="chat")
    model.get_model_schema = MagicMock(
        return_value=SimpleNamespace(features=[ModelFeature.VISION])
    )
    model._handle_generate_response = MagicMock(return_value="non-stream-result")
    model._handle_generate_stream_response = MagicMock(return_value=iter(["stream-result"]))
    return model


def _invoke(model_parameters: dict, stream: bool = False):
    model = _model()
    with patch("models.llm.llm.MultiModalConversation.call", return_value=MagicMock()) as call:
        model._generate(
            model="qwen4-max",
            credentials={"dashscope_api_key": "test-key"},
            prompt_messages=[UserPromptMessage(content="hello")],
            model_parameters=model_parameters,
            stream=stream,
        )
    return call.call_args.kwargs


def test_qwen4_max_schema() -> None:
    models_dir = Path(__file__).parent.parent / "models" / "llm"
    data = yaml.safe_load((models_dir / "qwen4-max.yaml").read_text())
    schema = AIModelEntity.model_validate(data)
    rules = {rule.name: rule for rule in schema.parameter_rules}

    assert schema.model == "qwen4-max"
    assert {
        ModelFeature.VISION,
        ModelFeature.VIDEO,
        ModelFeature.STRUCTURED_OUTPUT,
    }.issubset(schema.features or [])
    assert rules["max_completion_tokens"].max == 262144
    assert rules["enable_thinking"].default is True
    assert rules["reasoning_effort"].default == "high"
    assert rules["reasoning_effort"].options == ["low", "high", "xhigh"]
    assert "json_schema" in rules["response_format"].options

    position = (models_dir / "_position.yaml").read_text().splitlines()
    assert position[0] == "- qwen4-max"


def test_qwen4_max_defaults_to_thinking_without_preserved_thinking() -> None:
    kwargs = _invoke({})
    assert kwargs["enable_thinking"] is True
    assert kwargs["preserve_thinking"] is False
    assert kwargs["stream"] is True
    assert kwargs["incremental_output"] is True


def test_qwen4_max_drops_reasoning_effort_when_thinking_disabled() -> None:
    kwargs = _invoke({"enable_thinking": False, "reasoning_effort": "xhigh"})
    assert kwargs["enable_thinking"] is False
    assert "reasoning_effort" not in kwargs


def test_qwen4_max_keeps_reasoning_effort_when_thinking_enabled() -> None:
    kwargs = _invoke({"reasoning_effort": "xhigh"})
    assert kwargs["reasoning_effort"] == "xhigh"


def test_qwen4_max_does_not_apply_qwen38_temperature_floor() -> None:
    kwargs = _invoke({"temperature": 0.2})
    assert kwargs["temperature"] == 0.2
