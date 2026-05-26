import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dify_plugin.entities.model import ModelFeature
from dify_plugin.entities.model.message import UserPromptMessage

from models.llm.llm import TongyiLargeLanguageModel


QWEN3_OMNI_MODEL = "qwen3-omni-flash-2025-12-01"


def _model() -> TongyiLargeLanguageModel:
    model = TongyiLargeLanguageModel(model_schemas=MagicMock())
    model.get_model_mode = MagicMock(return_value="chat")
    model.get_model_schema = MagicMock(
        return_value=SimpleNamespace(features=[ModelFeature.VISION, ModelFeature.AUDIO])
    )
    model._handle_generate_response = MagicMock(return_value="non-stream-result")
    model._handle_generate_stream_response = MagicMock(return_value=iter(["stream-result"]))
    return model


def _invoke(model_parameters: dict, stream: bool = False):
    model = _model()
    with patch("models.llm.llm.MultiModalConversation.call", return_value=MagicMock()) as call:
        result = model._generate(
            model=QWEN3_OMNI_MODEL,
            credentials={"dashscope_api_key": "test-key"},
            prompt_messages=[UserPromptMessage(content="hello")],
            model_parameters=model_parameters,
            stream=stream,
        )
    return call.call_args.kwargs, result


def test_qwen3_omni_defaults_to_non_thinking_in_yaml() -> None:
    models_dir = Path(__file__).parent.parent / "models" / "llm"
    data = yaml.safe_load((models_dir / f"{QWEN3_OMNI_MODEL}.yaml").read_text())
    enable_thinking_rule = next(
        rule for rule in data["parameter_rules"] if rule["name"] == "enable_thinking"
    )
    assert enable_thinking_rule["default"] is False


def test_qwen3_omni_does_not_force_streaming_when_thinking_is_omitted() -> None:
    kwargs, result = _invoke({})
    assert kwargs["stream"] is False
    assert kwargs["incremental_output"] is False
    assert kwargs["enable_thinking"] is False
    assert kwargs["enable_omni_output_audio_url"] is True
    assert result == "non-stream-result"


def test_qwen3_omni_forces_streaming_when_thinking_is_enabled() -> None:
    kwargs, result = _invoke({"enable_thinking": True})
    assert kwargs["stream"] is True
    assert kwargs["incremental_output"] is True
    assert kwargs["enable_thinking"] is True
    assert "enable_omni_output_audio_url" not in kwargs
    assert list(result) == ["stream-result"]
