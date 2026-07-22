import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.llm import LLMResultChunk
from dify_plugin.entities.model.message import (
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageTool,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from google.genai import types
from models.llm.llm import GoogleLargeLanguageModel


ROOT = Path(__file__).resolve().parents[2]
MODELS = ("gemini-3.6-flash", "gemini-3.5-flash-lite")
RED_IMAGE = (
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAKElEQVR4nO3NsQ0A"
    "AAzCMP5/un0CNkuZ41wybXsHAAAAAAAAAAAAxR4yw/wuPL6QkAAAAABJRU5ErkJggg=="
)

pytestmark = pytest.mark.live

schemas = [
    AIModelEntity(
        **yaml.safe_load((ROOT / "models" / "llm" / f"{model}.yaml").read_text())
    )
    for model in MODELS
]
llm = GoogleLargeLanguageModel(schemas)


def _invoke(
    model: str,
    messages: list[PromptMessage],
    *,
    parameters: dict | None = None,
    tools: list[PromptMessageTool] | None = None,
    required_tool: str | None = None,
    stream: bool,
) -> list[LLMResultChunk]:
    def invoke() -> list[LLMResultChunk]:
        return list(
            llm.invoke(
                model=model,
                credentials={"google_api_key": os.environ["GEMINI_API_KEY"]},
                prompt_messages=messages,
                model_parameters=parameters
                or {"max_output_tokens": 128, "thinking_level": "Minimal"},
                tools=tools,
                stream=stream,
                user="gemini-live-test",
            )
        )

    if not required_tool:
        return invoke()

    original = llm._set_tool_calling

    def set_required_tool(*, config, model_parameters, tools) -> None:
        original(config=config, model_parameters=model_parameters, tools=tools)
        config.tool_config = types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.ANY,
                allowed_function_names=[required_tool],
            )
        )

    with patch.object(llm, "_set_tool_calling", side_effect=set_required_tool):
        return invoke()


def _text(chunks: list[LLMResultChunk]) -> str:
    texts = []
    for chunk in chunks:
        content = chunk.delta.message.content
        if isinstance(content, str):
            texts.append(content)
        elif content:
            texts.extend(
                part.data
                for part in content
                if isinstance(part, TextPromptMessageContent)
            )
    return "".join(texts)


def _assert_usage(chunks: list[LLMResultChunk]) -> None:
    usage = next(
        (chunk.delta.usage for chunk in reversed(chunks) if chunk.delta.usage), None
    )
    assert usage is not None
    assert usage.total_tokens > 0


@pytest.mark.parametrize("model", MODELS)
def test_streaming_text_generation(model: str) -> None:
    chunks = _invoke(
        model,
        [UserPromptMessage(content="Reply with OK.")],
        stream=True,
    )

    assert _text(chunks).strip()
    _assert_usage(chunks)


@pytest.mark.parametrize("model", MODELS)
def test_structured_output(model: str) -> None:
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string", "enum": ["OK"]}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    chunks = _invoke(
        model,
        [UserPromptMessage(content="Return the required structured answer.")],
        parameters={
            "max_output_tokens": 128,
            "thinking_level": "Minimal",
            "json_schema": json.dumps(schema),
        },
        stream=False,
    )

    assert json.loads(_text(chunks)) == {"answer": "OK"}
    _assert_usage(chunks)


@pytest.mark.parametrize("model", MODELS)
def test_inline_image_input(model: str) -> None:
    chunks = _invoke(
        model,
        [
            UserPromptMessage(
                content=[
                    ImagePromptMessageContent(
                        base64_data=RED_IMAGE,
                        format="png",
                        mime_type="image/png",
                        filename="red.png",
                    ),
                    TextPromptMessageContent(
                        data="Return only the primary color in this image."
                    ),
                ]
            )
        ],
        parameters={
            "max_output_tokens": 128,
            "thinking_level": "Minimal",
            "use_inline_file": True,
        },
        stream=False,
    )

    assert "RED" in _text(chunks).upper()
    _assert_usage(chunks)


@pytest.mark.parametrize("model", MODELS)
def test_tool_call_id_round_trip(model: str) -> None:
    tools = [
        PromptMessageTool(
            name="lookup_weather",
            description="Return the current weather for a city.",
            parameters={
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        )
    ]
    prompt = UserPromptMessage(
        content="Call lookup_weather exactly once for Paris before answering."
    )
    parameters = {"max_output_tokens": 512, "thinking_level": "Medium"}
    first = _invoke(
        model,
        [prompt],
        parameters=parameters,
        tools=tools,
        required_tool="lookup_weather",
        stream=False,
    )
    assistant = first[-1].delta.message
    calls = assistant.tool_calls

    assert calls
    assert all(call.function.name == "lookup_weather" for call in calls)
    assert all(call.id for call in calls)
    assert len({call.id for call in calls}) == len(calls)
    assert all(
        "paris" in json.loads(call.function.arguments)["city"].lower() for call in calls
    )
    _assert_usage(first)

    second = _invoke(
        model,
        [
            prompt,
            assistant,
            *[
                ToolPromptMessage(
                    name=call.function.name,
                    content='{"temperature_celsius": 21, "condition": "sunny"}',
                    tool_call_id=call.id,
                )
                for call in calls
            ],
        ],
        parameters=parameters,
        tools=tools,
        stream=True,
    )

    assert _text(second).strip()
    _assert_usage(second)
