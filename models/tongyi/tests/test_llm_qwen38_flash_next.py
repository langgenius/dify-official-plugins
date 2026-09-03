import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dify_plugin.entities.model import AIModelEntity, ModelFeature
from dify_plugin.entities.model.message import UserPromptMessage

from models.llm.llm import TongyiLargeLanguageModel


MODELS_DIR = Path(__file__).parent.parent / "models" / "llm"
MODEL_NAME = "qwen3.8-flash-next"


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _model() -> TongyiLargeLanguageModel:
    model = TongyiLargeLanguageModel(model_schemas=MagicMock())
    model.get_model_mode = MagicMock(return_value="chat")
    model.get_model_schema = MagicMock(
        return_value=SimpleNamespace(features=[ModelFeature.VISION, ModelFeature.VIDEO])
    )
    model._handle_generate_response = MagicMock(return_value="non-stream-result")
    model._handle_generate_stream_response = MagicMock(
        return_value=iter(["stream-result"])
    )
    return model


def _invoke(model_parameters: dict):
    model = _model()
    with patch(
        "models.llm.llm.MultiModalConversation.call", return_value=MagicMock()
    ) as call:
        result = model._generate(
            model=MODEL_NAME,
            credentials={"dashscope_api_key": "test-key"},
            prompt_messages=[UserPromptMessage(content="hello")],
            model_parameters=model_parameters,
            stream=False,
        )
    return call.call_args.kwargs, result


def test_qwen38_flash_next_schema() -> None:
    data = _load_yaml(MODELS_DIR / f"{MODEL_NAME}.yaml")
    schema = AIModelEntity.model_validate(data)
    rules = {rule.name: rule for rule in schema.parameter_rules}

    assert data["model"] == MODEL_NAME
    assert data["model_properties"]["context_size"] == 1_000_000
    assert {
        ModelFeature.VISION,
        ModelFeature.VIDEO,
        ModelFeature.STRUCTURED_OUTPUT,
    }.issubset(schema.features or [])
    assert rules["max_completion_tokens"].default == 8192
    assert rules["max_completion_tokens"].max == 131072
    assert rules["thinking_budget"].max == 262144
    assert rules["enable_thinking"].default is False
    assert rules["response_format"].options == ["text", "json_object", "json_schema"]
    assert data["pricing"] == {
        "input": "0.0008",
        "output": "0.0027",
        "unit": "0.001",
        "currency": "RMB",
    }

    model = _model()
    model.get_model_schema.return_value = schema
    assert model._validate_and_filter_model_parameters(
        MODEL_NAME,
        {"max_tokens": 128},
        {},
    ) == {"max_completion_tokens": 128}


def test_qwen38_flash_next_is_listed_after_qwen38_max() -> None:
    position = _load_yaml(MODELS_DIR / "_position.yaml")
    assert position.index("qwen3.8-flash-next") == position.index("qwen3.8-max") + 1


def test_qwen38_flash_next_defaults_to_non_thinking() -> None:
    kwargs, result = _invoke({})

    assert kwargs["enable_thinking"] is False
    assert kwargs["stream"] is False
    assert kwargs["incremental_output"] is False
    assert result == "non-stream-result"


def test_qwen38_flash_next_forces_streaming_when_thinking() -> None:
    kwargs, result = _invoke({"enable_thinking": True})

    assert kwargs["enable_thinking"] is True
    assert kwargs["stream"] is True
    assert kwargs["incremental_output"] is True
    assert list(result) == ["stream-result"]


def test_qwen38_flash_next_accepts_json_object_output() -> None:
    kwargs, result = _invoke({"response_format": "json_object"})

    assert kwargs["response_format"] == {"type": "json_object"}
    assert result == "non-stream-result"


def test_qwen38_flash_next_accepts_json_schema_output() -> None:
    output_schema = {
        "name": "answer",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
    }
    kwargs, result = _invoke(
        {
            "response_format": "json_schema",
            "json_schema": json.dumps(output_schema),
        }
    )

    assert kwargs["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "answer",
            "schema": output_schema["schema"],
        },
        "strict": True,
    }
    assert result == "non-stream-result"
