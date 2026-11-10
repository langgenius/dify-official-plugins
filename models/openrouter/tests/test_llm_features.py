import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from dify_plugin.entities.model import AIModelEntity, ModelFeature
from dify_plugin.entities.model.message import (
    ImagePromptMessageContent,
    TextPromptMessageContent,
    UserPromptMessage,
    VideoPromptMessageContent,
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


def test_custom_model_form_exposes_optional_video_input() -> None:
    provider = Path(__file__).resolve().parent.parent / "provider" / "openrouter.yaml"
    fields = yaml.safe_load(provider.read_text(encoding="utf-8"))["model_credential_schema"][
        "credential_form_schemas"
    ]
    video = next(field for field in fields if field["variable"] == "video_support")
    assert video["default"] == "no_support"
    assert {choice["value"] for choice in video["options"]} == {"support", "no_support"}


@pytest.mark.parametrize(
    ("vision", "video", "expected_media"),
    [
        ("no_support", None, []),
        ("support", None, ["image_url", "video_url"]),
        ("support", "no_support", ["image_url"]),
        ("no_support", "support", ["video_url"]),
        ("support", "support", ["image_url", "video_url"]),
    ],
)
def test_custom_model_media_routing(
    llm: OpenRouterLargeLanguageModel, vision: str, video: str | None, expected_media: list[str]
) -> None:
    credentials = {
        "mode": "chat",
        "api_key": "test",
        "context_size": "4096",
        "vision_support": vision,
    }
    if video:
        credentials["video_support"] = video
    model = "custom/multimodal"
    schema = llm.get_customizable_model_schema(model, credentials)
    assert (ModelFeature.VIDEO in (schema.features or [])) == (video == "support")
    message = UserPromptMessage(
        content=[
            TextPromptMessageContent(data="Describe the clip"),
            ImagePromptMessageContent(format="png", mime_type="image/png", base64_data="aW1hZ2U="),
            VideoPromptMessageContent(format="mp4", mime_type="video/mp4", base64_data="dmlkZW8="),
        ]
    )
    with patch("requests.post") as post:
        post.return_value.status_code = 200
        llm._invoke(model, credentials, [message], {}, stream=True)
    request = json.loads(post.call_args.kwargs["data"])
    body = request["messages"][0]["content"]
    media = [part for part in body if part["type"] != "text"] if isinstance(body, list) else []
    assert [part["type"] for part in media] == expected_media
    if video == "support":
        assert media[-1]["video_url"]["url"] == "data:video/mp4;base64,dmlkZW8="


def test_catalog_vision_model_keeps_existing_media_routing() -> None:
    catalog = next(item for item in _llm_schemas() if item["model"] == "openai/chatgpt-4o-latest")
    schema = AIModelEntity.model_validate(catalog)
    assert (
        ModelFeature.VISION in (schema.features or []) and ModelFeature.VIDEO not in schema.features
    )
    llm = OpenRouterLargeLanguageModel(model_schemas=[schema])
    message = UserPromptMessage(
        content=[
            VideoPromptMessageContent(
                format="mp4",
                mime_type="video/mp4",
                url="https://example.com/clip.mp4",
            )
        ]
    )
    with patch("requests.post") as post:
        post.return_value.status_code = 200
        llm._invoke(schema.model, {"api_key": "test"}, [message], {}, stream=True)
    assert json.loads(post.call_args.kwargs["data"])["messages"][0]["content"] == [
        {"type": "video_url", "video_url": {"url": "https://example.com/clip.mp4"}},
    ]


def test_set_service_tier_params_sends_flex() -> None:
    model_parameters = {"service_tier": "flex", "temperature": 0.2}

    OpenRouterLargeLanguageModel._set_service_tier_params(model_parameters)

    assert model_parameters == {"service_tier": "flex", "temperature": 0.2}


@pytest.mark.parametrize("service_tier", ["auto", None, "", "priority"])
def test_set_service_tier_params_leaves_routing_unchanged_otherwise(
    service_tier: str | None,
) -> None:
    model_parameters = {"service_tier": service_tier, "temperature": 0.2}

    OpenRouterLargeLanguageModel._set_service_tier_params(model_parameters)

    assert model_parameters == {"temperature": 0.2}


def test_service_tier_rules_default_to_auto_and_offer_flex() -> None:
    rules = [
        rule
        for schema in _llm_schemas()
        for rule in schema["parameter_rules"]
        if rule["name"] == "service_tier"
    ]

    assert rules
    for rule in rules:
        assert rule["default"] == "auto"
        assert rule["options"] == ["auto", "flex"]


def test_invoke_sends_flex_service_tier(llm: OpenRouterLargeLanguageModel) -> None:
    schema_path = (
        Path(__file__).resolve().parent.parent / "models" / "llm" / "gpt-6-luna.yaml"
    )
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    model_schema = llm.get_customizable_model_schema(
        schema["model"],
        {"mode": "chat", "context_size": "128000", "max_tokens_to_sample": "8192"},
    )

    with (
        patch.object(llm, "_update_credential"),
        patch.object(llm, "get_model_schema", return_value=model_schema),
        patch.object(llm, "_generate", return_value="result") as generate,
    ):
        llm._invoke(
            model=schema["model"],
            credentials={},
            prompt_messages=[UserPromptMessage(content="Hi")],
            model_parameters={"service_tier": "flex"},
        )

    sent_parameters = generate.call_args.args[3]
    assert sent_parameters["service_tier"] == "flex"
    assert sent_parameters["provider"] == {"data_collection": "allow"}


def test_custom_model_exposes_service_tier(llm: OpenRouterLargeLanguageModel) -> None:
    schema = llm.get_customizable_model_schema(
        "custom/flex-model",
        {"mode": "chat", "context_size": "128000", "max_tokens_to_sample": "8192"},
    )

    rules = {rule.name: rule for rule in schema.parameter_rules}
    assert rules["service_tier"].options == ["auto", "flex"]
    assert rules["service_tier"].default == "auto"
