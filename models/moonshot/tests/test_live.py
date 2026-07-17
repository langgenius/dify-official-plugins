import json
import os
import sys
from pathlib import Path

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import UserPromptMessage
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.llm.llm import MoonshotLargeLanguageModel  # noqa: E402

MODEL = "kimi-k2.7-code"


def _api_key() -> str:
    if value := os.getenv("MOONSHOT_API_KEY", "").strip():
        return value
    value = dotenv_values(ROOT / ".env").get("MOONSHOT_API_KEY")
    return value.strip() if value else ""


API_KEY = _api_key()
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not API_KEY,
        reason="MOONSHOT_API_KEY is missing from the environment and .env",
    ),
]


class _Credentials(dict[str, str]):
    def __repr__(self) -> str:
        return "Moonshot live test credentials"

    __str__ = __repr__


schema = AIModelEntity.model_validate(
    yaml.safe_load((ROOT / "models" / "llm" / f"{MODEL}.yaml").read_text()),
)
llm = MoonshotLargeLanguageModel(model_schemas=[schema])


def _invoke(*, stream: bool, parameters: dict) -> list:
    return list(
        llm.invoke(
            model=MODEL,
            credentials=_Credentials(api_key=API_KEY),
            prompt_messages=[UserPromptMessage(content="Reply with OK.")],
            model_parameters=parameters,
            stream=stream,
        ),
    )


def _text(chunks: list) -> str:
    return "".join(
        chunk.delta.message.content
        for chunk in chunks
        if isinstance(chunk.delta.message.content, str)
    )


def _assert_usage(chunks: list) -> None:
    assert any(
        chunk.delta.usage and chunk.delta.usage.total_tokens > 0 for chunk in chunks
    )


def test_blocking_completion() -> None:
    chunks = _invoke(
        stream=False,
        parameters={"max_completion_tokens": 256},
    )

    content, _ = llm._extract_reasoning_content(_text(chunks))
    assert content.strip()
    _assert_usage(chunks)


def test_streaming_structured_output() -> None:
    output_schema = {
        "name": "moonshot_live_test",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"answer": {"type": "string", "enum": ["OK"]}},
            "required": ["answer"],
            "additionalProperties": False,
        },
    }
    chunks = _invoke(
        stream=True,
        parameters={
            "max_completion_tokens": 512,
            "response_format": "json_schema",
            "json_schema": json.dumps(output_schema),
        },
    )

    content, _ = llm._extract_reasoning_content(_text(chunks))
    assert json.loads(content) == {"answer": "OK"}
    _assert_usage(chunks)
