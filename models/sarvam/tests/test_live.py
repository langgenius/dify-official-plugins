import json
import os

import pytest

from dify_plugin.entities.model.message import (
    ImagePromptMessageContent,
    PromptMessageTool,
    TextPromptMessageContent,
    UserPromptMessage,
)
from models.llm.llm import SarvamLargeLanguageModel

pytestmark = pytest.mark.live

API_KEY = os.getenv("SARVAM_API_KEY")
MODELS = [
    "sarvam-105b",
    "sarvam-105b-conversations",
    "glm5.3",
    "glm5.3-flash",
    "gemma4",
    "deepseekv4.1-flash-1017",
    "deepseekv4.1-flash-1017-interactive",
]
REASONING_MODELS = {
    "sarvam-105b",
    "glm5.3",
    "glm5.3-flash",
    "gemma4",
    "deepseekv4.1-flash-1017",
    "deepseekv4.1-flash-1017-interactive",
}

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not API_KEY, reason="SARVAM_API_KEY is not set"),
]


def invoke(model: str, parameters: dict, **overrides):
    llm = SarvamLargeLanguageModel(model_schemas=[])
    params = {
        "model": model,
        "credentials": {"api_key": API_KEY},
        "prompt_messages": [UserPromptMessage(content="Reply with exactly OK")],
        "model_parameters": parameters,
        "stream": False,
    }
    params.update(overrides)
    return llm._invoke(**params)


@pytest.mark.parametrize("model", MODELS)
def test_live_non_stream(model: str) -> None:
    parameters = {"max_tokens": 1024}
    if model in REASONING_MODELS:
        parameters["reasoning_effort"] = "low"
    result = invoke(model, parameters)
    assert result.usage.prompt_tokens > 0
    assert result.message.content is not None


def test_live_stream() -> None:
    chunks = list(
        invoke(
            "sarvam-105b",
            {"max_tokens": 512, "reasoning_effort": "low"},
            stream=True,
        )
    )
    assert chunks
    text = "".join(chunk.delta.message.content or "" for chunk in chunks)
    assert text


def test_live_tool_call() -> None:
    tool = PromptMessageTool(
        name="ping",
        description="Return a ping marker.",
        parameters={"type": "object", "properties": {}},
    )
    result = invoke(
        "glm5.3-flash",
        {"max_tokens": 512, "reasoning_effort": "low"},
        prompt_messages=[UserPromptMessage(content="Call ping exactly once.")],
        tools=[tool],
    )
    assert result.message.tool_calls
    assert result.message.tool_calls[0].function.name == "ping"


def test_live_vision() -> None:
    image = ImagePromptMessageContent(
        format="png",
        mime_type="image/png",
        base64_data=(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        ),
    )
    result = invoke(
        "gemma4",
        {"max_tokens": 128, "reasoning_effort": "none"},
        prompt_messages=[
            UserPromptMessage(
                content=[
                    TextPromptMessageContent(data="What color is this image?"),
                    image,
                ]
            )
        ],
    )
    assert result.message.content


def test_live_json_object() -> None:
    result = invoke(
        "sarvam-105b",
        {
            "max_tokens": 256,
            "reasoning_effort": "none",
            "response_format": "json_object",
        },
        prompt_messages=[UserPromptMessage(content='Return {"ok": true} as JSON')],
    )
    assert json.loads(result.message.content) == {"ok": True}
