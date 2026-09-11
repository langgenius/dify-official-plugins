import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
    VideoPromptMessageContent,
)

PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from models.llm.llm import ZhipuAILargeLanguageModel


def test_glm_5_2_schema_and_request_parameters() -> None:
    model_file = PLUGIN_DIR / "models" / "llm" / "glm-5.2.yaml"
    schema = yaml.safe_load(model_file.read_text(encoding="utf-8"))
    AIModelEntity.model_validate(schema)

    position = yaml.safe_load(
        (model_file.parent / "_position.yaml").read_text(encoding="utf-8")
    )
    assert position[:3] == ["glm-5.3", "glm-5.3-flash", "glm-5.2"]

    rules = {rule["name"]: rule for rule in schema["parameter_rules"]}
    assert schema["model_properties"]["context_size"] == 1_000_000
    assert rules["max_tokens"]["default"] == 65_536
    assert rules["max_tokens"]["max"] == 131_072
    assert rules["thinking"]["default"] is True
    assert rules["reasoning_effort"]["options"] == [
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    ]
    assert rules["reasoning_effort"]["default"] == "max"
    assert rules["response_format"]["options"] == ["text", "json_object"]
    assert schema["pricing"] == {
        "input": "0.008",
        "output": "0.028",
        "unit": "0.001",
        "currency": "RMB",
    }

    client = MagicMock()
    result = object()
    llm = ZhipuAILargeLanguageModel(model_schemas=[])
    with (
        patch("models.llm.llm.ZhipuAiClient", return_value=client),
        patch.object(
            ZhipuAILargeLanguageModel,
            "_handle_generate_response",
            return_value=result,
        ),
    ):
        actual = llm._generate(
            model="glm-5.2",
            credentials_kwargs={"api_key": "test-key"},
            prompt_messages=[UserPromptMessage(content="hello")],
            model_parameters={"thinking": False, "reasoning_effort": "none"},
            stream=False,
        )

    assert actual is result
    client.chat.completions.create.assert_called_once_with(
        model="glm-5.2",
        messages=[{"role": "user", "content": "hello"}],
        thinking={"type": "disabled"},
        reasoning_effort="none",
    )


def test_glm_5_3_schema_and_request_parameters() -> None:
    model_file = PLUGIN_DIR / "models" / "llm" / "glm-5.3.yaml"
    schema = yaml.safe_load(model_file.read_text(encoding="utf-8"))
    AIModelEntity.model_validate(schema)

    position = yaml.safe_load(
        (model_file.parent / "_position.yaml").read_text(encoding="utf-8")
    )
    assert position[0] == "glm-5.3"

    rules = {rule["name"]: rule for rule in schema["parameter_rules"]}
    assert schema["model_properties"]["context_size"] == 1_000_000
    assert rules["max_tokens"]["default"] == 65_536
    assert rules["max_tokens"]["max"] == 131_072
    assert rules["reasoning_effort"]["options"] == ["low", "high", "max"]
    assert rules["reasoning_effort"]["default"] == "max"
    assert "thinking" not in rules
    assert schema["pricing"] == {
        "input": "0.008",
        "output": "0.028",
        "unit": "0.001",
        "currency": "RMB",
    }

    client = MagicMock()
    result = object()
    llm = ZhipuAILargeLanguageModel(model_schemas=[])
    with (
        patch("models.llm.llm.ZhipuAiClient", return_value=client),
        patch.object(
            ZhipuAILargeLanguageModel,
            "_handle_generate_response",
            return_value=result,
        ),
    ):
        actual = llm._generate(
            model="glm-5.3",
            credentials_kwargs={"api_key": "test-key"},
            prompt_messages=[UserPromptMessage(content="hello")],
            model_parameters={"thinking": False, "reasoning_effort": "low"},
            stream=False,
        )

    assert actual is result
    client.chat.completions.create.assert_called_once_with(
        model="glm-5.3",
        messages=[{"role": "user", "content": "hello"}],
        thinking={"type": "enabled"},
        reasoning_effort="low",
    )


def test_glm_5_3_flash_schema_and_request_parameters() -> None:
    model_file = PLUGIN_DIR / "models" / "llm" / "glm-5.3-flash.yaml"
    schema = yaml.safe_load(model_file.read_text(encoding="utf-8"))
    AIModelEntity.model_validate(schema)

    assert schema["features"][:2] == ["vision", "video"]
    assert "document" not in schema["features"]
    assert schema["model_properties"]["context_size"] == 1_000_000
    rules = {rule["name"]: rule for rule in schema["parameter_rules"]}
    assert rules["max_tokens"] == {
        "name": "max_tokens",
        "use_template": "max_tokens",
        "default": 65_536,
        "min": 1,
        "max": 131_072,
    }
    assert rules["reasoning_effort"]["options"] == ["low", "high", "max"]
    assert rules["reasoning_effort"]["default"] == "max"
    assert schema["pricing"] == {
        "input": "0.0008",
        "output": "0.0028",
        "unit": "0.001",
        "currency": "RMB",
    }

    image = ImagePromptMessageContent(
        url="https://example.com/image.png",
        mime_type="image/png",
        format="png",
    )
    tool_call = AssistantPromptMessage.ToolCall(
        id="call_1",
        type="function",
        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
            name="read_document",
            arguments='{"page": 1}',
        ),
    )
    client = MagicMock()
    result = object()
    llm = ZhipuAILargeLanguageModel(model_schemas=[])
    with (
        patch("models.llm.llm.ZhipuAiClient", return_value=client),
        patch.object(
            ZhipuAILargeLanguageModel,
            "_handle_generate_response",
            return_value=result,
        ),
    ):
        actual = llm._generate(
            model="glm-5.3-flash",
            credentials_kwargs={"api_key": "test-key"},
            prompt_messages=[
                UserPromptMessage(content=[image]),
                UserPromptMessage(content="describe it"),
                AssistantPromptMessage(content="", tool_calls=[tool_call]),
                ToolPromptMessage(content='{"status": "ok"}', tool_call_id="call_1"),
            ],
            model_parameters={"reasoning_effort": "low"},
            stream=False,
        )

    assert actual is result
    client.chat.completions.create.assert_called_once_with(
        model="glm-5.3-flash",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.com/image.png"},
                    },
                    {"type": "text", "text": "describe it"},
                ],
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "read_document",
                            "arguments": '{"page": 1}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "content": '{"status": "ok"}',
                "tool_call_id": "call_1",
            },
        ],
        thinking={"type": "enabled"},
        reasoning_effort="low",
    )


def test_zhipuai_video_requires_url() -> None:
    video = VideoPromptMessageContent(
        base64_data="dmlkZW8=",
        mime_type="video/mp4",
        format="mp4",
    )
    llm = ZhipuAILargeLanguageModel(model_schemas=[])

    with pytest.raises(ValueError, match="MULTIMODAL_SEND_FORMAT=url"):
        llm._construct_multimodal_content("glm-5.3-flash", [video])
