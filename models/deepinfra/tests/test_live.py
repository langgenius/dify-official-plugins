"""Live checks against the DeepInfra API.

Skipped unless both RUN_DEEPINFRA_LIVE=1 and DEEPINFRA_API_KEY are set, so CI
runs the catalog tests only.

`invoke()` always yields LLMResultChunk, for streaming and blocking calls alike,
so every assertion works off the collected chunk list.

Provider-level credential validation is not exercised directly: ModelProvider
requires the plugin runtime to construct. It calls the same
`OpenAI(...).models.list()` as the model-level checks below.
"""

import json
import os
import sys
from pathlib import Path

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.llm import LLMResultChunk
from dify_plugin.entities.model.message import PromptMessageTool, UserPromptMessage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.llm.llm import DeepInfraLargeLanguageModel  # noqa: E402
from models.text_embedding.text_embedding import DeepInfraTextEmbeddingModel  # noqa: E402

API_KEY = os.getenv("DEEPINFRA_API_KEY", "").strip()
LIVE_ENABLED = os.getenv("RUN_DEEPINFRA_LIVE") == "1"

pytestmark = [
    pytest.mark.skipif(
        not (API_KEY and LIVE_ENABLED),
        reason="set RUN_DEEPINFRA_LIVE=1 and DEEPINFRA_API_KEY",
    ),
]

CHAT_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
VISION_MODEL = "meta-llama/Llama-4-Scout-17B-16E-Instruct"
EMBED_MODEL = "BAAI/bge-m3"


class _Credentials(dict[str, str]):
    """Keeps the key out of pytest assertion output."""

    def __repr__(self) -> str:
        return "DeepInfra live test credentials"

    __str__ = __repr__


def _schemas(kind: str) -> list[AIModelEntity]:
    directory = ROOT / "models" / kind
    return [
        AIModelEntity.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in directory.glob("*.yaml")
        if path.name != "_position.yaml"
    ]


@pytest.fixture(scope="module")
def credentials() -> dict[str, str]:
    return _Credentials(api_key=API_KEY)


@pytest.fixture(scope="module")
def llm() -> DeepInfraLargeLanguageModel:
    return DeepInfraLargeLanguageModel(model_schemas=_schemas("llm"))


@pytest.fixture(scope="module")
def embedding() -> DeepInfraTextEmbeddingModel:
    return DeepInfraTextEmbeddingModel(model_schemas=_schemas("text_embedding"))


def _text(chunks: list[LLMResultChunk]) -> str:
    return "".join(
        chunk.delta.message.content
        for chunk in chunks
        if isinstance(chunk.delta.message.content, str)
    )


def _usage(chunks: list[LLMResultChunk]):
    assert chunks, "no chunks returned"
    usage = chunks[-1].delta.usage
    assert usage is not None, "final chunk carries no usage"
    return usage


def _invoke(llm, credentials, messages, *, model=CHAT_MODEL, parameters, tools=None, stream):
    return list(
        llm.invoke(
            model=model,
            credentials=dict(credentials),
            prompt_messages=messages,
            model_parameters=parameters,
            tools=tools,
            stream=stream,
            user="deepinfra-live-test",
        )
    )


def test_llm_validate_credentials(llm, credentials) -> None:
    llm.validate_credentials(model=CHAT_MODEL, credentials=dict(credentials))


def test_llm_blocking_invoke(llm, credentials) -> None:
    chunks = _invoke(
        llm,
        credentials,
        [UserPromptMessage(content="Reply with exactly: OK")],
        parameters={"temperature": 0.0, "max_tokens": 32},
        stream=False,
    )
    assert "OK" in _text(chunks)
    assert _usage(chunks).total_tokens > 0


def test_llm_stream_invoke(llm, credentials) -> None:
    chunks = _invoke(
        llm,
        credentials,
        [UserPromptMessage(content="Count: 1 2 3")],
        parameters={"temperature": 0.0, "max_tokens": 64},
        stream=True,
    )
    assert _text(chunks).strip()
    assert _usage(chunks).total_tokens > 0


def test_llm_tool_call(llm, credentials) -> None:
    tool = PromptMessageTool(
        name="get_weather",
        description="Get the current weather for a city",
        parameters={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    )
    chunks = _invoke(
        llm,
        credentials,
        [UserPromptMessage(content="What is the weather in Tokyo?")],
        parameters={"temperature": 0.0, "max_tokens": 128},
        tools=[tool],
        stream=False,
    )
    calls = [call for chunk in chunks for call in (chunk.delta.message.tool_calls or [])]
    assert calls, "expected the model to emit a tool call"
    assert calls[0].function.name == "get_weather"


def test_llm_stream_tool_call(llm, credentials) -> None:
    """tool_calls stream in fragments, so verify they reassemble into one call."""
    tool = PromptMessageTool(
        name="get_weather",
        description="Get the current weather for a city",
        parameters={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    )
    chunks = _invoke(
        llm,
        credentials,
        [UserPromptMessage(content="What is the weather in Tokyo?")],
        parameters={"temperature": 0.0, "max_tokens": 128},
        tools=[tool],
        stream=True,
    )
    calls = [call for chunk in chunks for call in (chunk.delta.message.tool_calls or [])]
    assert calls, "expected a tool call to be reassembled from the stream"
    assert calls[0].function.name == "get_weather"
    assert calls[0].id, "tool call id must survive reassembly"
    assert json.loads(calls[0].function.arguments)["city"], "arguments must reassemble into valid JSON"


def test_llm_vision_invoke(llm, credentials) -> None:
    """A 1x1 red PNG, to confirm image parts reach a vision model intact."""
    from dify_plugin.entities.model.message import ImagePromptMessageContent, TextPromptMessageContent

    png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    chunks = _invoke(
        llm,
        credentials,
        [
            UserPromptMessage(
                content=[
                    TextPromptMessageContent(data="What colour is this image? One word."),
                    ImagePromptMessageContent(url=png, mime_type="image/png", format="png"),
                ]
            )
        ],
        model=VISION_MODEL,
        parameters={"temperature": 0.0, "max_tokens": 32},
        stream=False,
    )
    assert _text(chunks).strip()


def test_embedding_validate_credentials(embedding, credentials) -> None:
    embedding.validate_credentials(model=EMBED_MODEL, credentials=dict(credentials))


def test_embedding_invoke(embedding, credentials) -> None:
    result = embedding.invoke(
        model=EMBED_MODEL,
        credentials=dict(credentials),
        texts=["hello world", "こんにちは"],
    )
    assert len(result.embeddings) == 2
    assert len(result.embeddings[0]) == 1024
    assert result.usage.total_tokens > 0
