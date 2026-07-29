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


QWEN3_VL_HYBRID_THINKING_MODELS = [
    "qwen3-vl-plus",
    "qwen3-vl-plus-2025-09-23",
    "qwen3-vl-flash",
]


def _model() -> TongyiLargeLanguageModel:
    model = TongyiLargeLanguageModel(model_schemas=MagicMock())
    model.get_model_mode = MagicMock(return_value="chat")
    model.get_model_schema = MagicMock(
        return_value=SimpleNamespace(features=[ModelFeature.VISION])
    )
    model._handle_generate_response = MagicMock(return_value="non-stream-result")
    model._handle_generate_stream_response = MagicMock(return_value=iter(["stream-result"]))
    return model


def _invoke(model_name: str, model_parameters: dict, stream: bool = False):
    model = _model()
    with patch("models.llm.llm.MultiModalConversation.call", return_value=MagicMock()) as call:
        result = model._generate(
            model=model_name,
            credentials={"dashscope_api_key": "test-key"},
            prompt_messages=[UserPromptMessage(content="hello")],
            model_parameters=model_parameters,
            stream=stream,
        )
    return call.call_args.kwargs, result


def test_qwen3_vl_hybrid_models_default_to_non_thinking_in_yaml() -> None:
    models_dir = Path(__file__).parent.parent / "models" / "llm"
    for model_name in QWEN3_VL_HYBRID_THINKING_MODELS:
        data = yaml.safe_load((models_dir / f"{model_name}.yaml").read_text())
        enable_thinking_rule = next(
            rule for rule in data["parameter_rules"] if rule["name"] == "enable_thinking"
        )
        assert enable_thinking_rule["default"] is False


def test_qwen3_vl_hybrid_models_do_not_force_streaming_when_thinking_is_omitted() -> None:
    for model_name in QWEN3_VL_HYBRID_THINKING_MODELS:
        kwargs, result = _invoke(model_name, {})
        assert kwargs["stream"] is False
        assert kwargs["incremental_output"] is False
        assert kwargs["enable_thinking"] is False
        assert result == "non-stream-result"


def test_qwen3_vl_hybrid_models_force_streaming_when_thinking_is_enabled() -> None:
    for model_name in QWEN3_VL_HYBRID_THINKING_MODELS:
        kwargs, result = _invoke(model_name, {"enable_thinking": True})
        assert kwargs["stream"] is True
        assert kwargs["incremental_output"] is True
        assert kwargs["enable_thinking"] is True
        assert list(result) == ["stream-result"]
