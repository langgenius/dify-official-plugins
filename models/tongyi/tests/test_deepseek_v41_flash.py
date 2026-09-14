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

MODEL = "deepseek-v4.1-flash"
MODELS_DIR = Path(__file__).parent.parent / "models" / "llm"


def _load_data() -> dict:
    return yaml.safe_load((MODELS_DIR / f"{MODEL}.yaml").read_text(encoding="utf-8"))


def _load_schema() -> AIModelEntity:
    return AIModelEntity.model_validate(_load_data())


def _model() -> TongyiLargeLanguageModel:
    model = TongyiLargeLanguageModel(model_schemas=MagicMock())
    model.get_model_mode = MagicMock(return_value="chat")
    model.get_model_schema = MagicMock(
        return_value=SimpleNamespace(features=[ModelFeature.VISION])
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
            model=MODEL,
            credentials={"dashscope_api_key": "test-key"},
            prompt_messages=[UserPromptMessage(content="hello")],
            model_parameters=model_parameters,
            stream=False,
        )
    return call.call_args.kwargs, result


def test_schema_matches_deepseek_v41_flash_capabilities() -> None:
    data = _load_data()
    schema = _load_schema()
    rules = {rule.name: rule for rule in schema.parameter_rules}

    assert schema.model == MODEL
    assert data["model_properties"]["context_size"] == 1_000_000
    assert {
        ModelFeature.VISION,
        ModelFeature.STRUCTURED_OUTPUT,
        ModelFeature.AGENT_THOUGHT,
        ModelFeature.TOOL_CALL,
        ModelFeature.MULTI_TOOL_CALL,
        ModelFeature.STREAM_TOOL_CALL,
    }.issubset(schema.features or [])
    assert rules["max_completion_tokens"].default == 393_216
    assert rules["max_completion_tokens"].max == 393_216
    assert rules["reasoning_effort"].type.value == "int"
    assert (rules["reasoning_effort"].min, rules["reasoning_effort"].max) == (1, 100)
    assert rules["enable_thinking"].default is True
    assert rules["response_format"].options == ["text", "json_object"]
    assert "top_k" not in rules
    assert data["pricing"] == {
        "input": "0.002",
        "output": "0.008",
        "unit": "0.001",
        "currency": "RMB",
    }


def test_max_tokens_is_mapped_to_max_completion_tokens() -> None:
    model = _model()
    model.get_model_schema.return_value = _load_schema()

    assert model._validate_and_filter_model_parameters(
        MODEL,
        {"max_tokens": 128},
        {},
    ) == {"max_completion_tokens": 128}


def test_thinking_defaults_to_enabled_and_forces_streaming() -> None:
    kwargs, result = _invoke({"reasoning_effort": 42})

    # The DashScope API defaults this model to thinking mode when the field is
    # omitted, and the adapter uses that same default for its stream decision.
    assert kwargs.get("enable_thinking", True) is True
    assert kwargs["reasoning_effort"] == 42
    assert kwargs["stream"] is True
    assert kwargs["incremental_output"] is True
    assert list(result) == ["stream-result"]


def test_thinking_can_be_disabled() -> None:
    kwargs, result = _invoke({"enable_thinking": False, "reasoning_effort": 42})

    assert kwargs["enable_thinking"] is False
    assert kwargs["reasoning_effort"] == 42
    assert kwargs["stream"] is False
    assert kwargs["incremental_output"] is False
    assert result == "non-stream-result"


def test_json_object_output_is_forwarded() -> None:
    kwargs, result = _invoke(
        {"enable_thinking": False, "response_format": "json_object"}
    )

    assert kwargs["response_format"] == {"type": "json_object"}
    assert result == "non-stream-result"
