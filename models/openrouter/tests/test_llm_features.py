import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from dify_plugin.entities.model import ModelFeature
from dify_plugin.entities.model.message import (
    ImagePromptMessageContent,
    TextPromptMessageContent,
    UserPromptMessage,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.llm.llm import OpenRouterLargeLanguageModel


@pytest.fixture
def llm() -> OpenRouterLargeLanguageModel:
    return OpenRouterLargeLanguageModel(model_schemas=[])


def _llm_schemas() -> list[dict]:
    llm_dir = Path(__file__).resolve().parent.parent / "models" / "llm"
    return [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(llm_dir.glob("*.yaml"))
        if not path.name.startswith("_")
    ]


def _declared_efforts() -> list[str]:
    efforts = set()
    for schema in _llm_schemas():
        for rule in schema["parameter_rules"]:
            if rule["name"] == "reasoning_effort":
                efforts.update(rule["options"])
    return sorted(efforts)


@pytest.mark.parametrize("effort", _declared_efforts())
def test_set_reasoning_params_supports_requested_effort_levels(effort: str) -> None:
    model_parameters = {
        "reasoning_effort": effort,
        "exclude_reasoning_tokens": True,
        "temperature": 0.2,
    }

    OpenRouterLargeLanguageModel._set_reasoning_params(model_parameters)

    assert model_parameters == {
        "reasoning": {"effort": effort, "exclude": True},
        "temperature": 0.2,
    }


def test_position_list_matches_shipped_model_schemas() -> None:
    llm_dir = Path(__file__).resolve().parent.parent / "models" / "llm"
    positions = yaml.safe_load((llm_dir / "_position.yaml").read_text(encoding="utf-8"))
    schemas = {schema["model"]: schema for schema in _llm_schemas()}

    assert [model for model in positions if model not in schemas] == []
    assert [model for model in positions if schemas[model].get("deprecated")] == []


def test_minimax_m3_exposes_reasoning_and_vision_controls() -> None:
    schema_path = (
        Path(__file__).resolve().parent.parent / "models" / "llm" / "minimax-m3.yaml"
    )
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    rules = {rule["name"]: rule for rule in schema["parameter_rules"]}

    assert "vision" in schema["features"]
    assert rules["reasoning_effort"]["options"] == ["low", "medium", "high"]
    assert rules["exclude_reasoning_tokens"]["default"] is True


def test_custom_reasoning_model_exposes_effort_and_hide_controls(
    llm: OpenRouterLargeLanguageModel,
) -> None:
    schema = llm.get_customizable_model_schema(
        "custom/reasoning-model",
        {
            "mode": "chat",
            "context_size": "128000",
            "max_tokens_to_sample": "8192",
            "reasoning_support": "support",
        },
    )

    rules = {rule.name: rule for rule in schema.parameter_rules}
    assert ModelFeature.AGENT_THOUGHT in (schema.features or [])
    assert rules["reasoning_effort"].options == ["low", "medium", "high"]
    assert rules["exclude_reasoning_tokens"].default is True


def test_custom_vision_model_keeps_uploaded_images(
    llm: OpenRouterLargeLanguageModel,
) -> None:
    credentials = {
        "mode": "chat",
        "context_size": "128000",
        "max_tokens_to_sample": "8192",
        "vision_support": "support",
    }
    vision_schema = llm.get_customizable_model_schema(
        "custom/vision-model", credentials
    )
    assert ModelFeature.VISION in (vision_schema.features or [])

    prompt_messages = [
        UserPromptMessage(
            content=[
                TextPromptMessageContent(data="What is in this image?"),
                ImagePromptMessageContent(
                    format="png",
                    mime_type="image/png",
                    base64_data="aW1hZ2U=",
                ),
            ]
        )
    ]

    with (
        patch.object(llm, "_update_credential"),
        patch.object(llm, "get_model_schema", return_value=vision_schema),
        patch.object(llm, "_generate", return_value="result") as generate,
    ):
        result = llm._invoke(
            model="custom/vision-model",
            credentials=credentials,
            prompt_messages=prompt_messages,
            model_parameters={},
        )

    assert result == "result"
    assert generate.call_args.args[2] is prompt_messages
    sent_content = generate.call_args.args[2][0].content
    assert isinstance(sent_content, list)
    assert any(isinstance(part, ImagePromptMessageContent) for part in sent_content)
