from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from dify_plugin.entities.model.llm import LLMUsage
from dify_plugin.entities.model.message import UserPromptMessage

ROOT = Path(__file__).resolve().parents[1]
LIVE_TESTS = ROOT / "tests" / "live"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.llm import stream as response_stream  # noqa: E402
from models.llm.llm import OpenAILargeLanguageModel  # noqa: E402

_DEFAULT_USAGE = object()


def _load_live_environment() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator or name.strip() not in {
            "OPENAI_API_KEY",
            "OPENAI_ORGANIZATION",
            "OPENAI_BASE_URL",
            "OPENAI_API_BASE",
        }:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        name = name.strip()
        if not os.getenv(name, "").strip():
            os.environ[name] = value


def _has_live_api_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def pytest_configure() -> None:
    _load_live_environment()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    enabled = _has_live_api_key()
    skipped = pytest.mark.skip(
        reason="OPENAI_API_KEY is missing or empty in .env and the environment"
    )
    for item in items:
        in_live_directory = Path(str(item.path)).resolve().is_relative_to(LIVE_TESTS)
        marked_live = item.get_closest_marker("live") is not None
        if in_live_directory and not marked_live:
            item.add_marker(pytest.mark.live)
        if not enabled and (in_live_directory or marked_live):
            item.add_marker(skipped)


class FakeStream(Iterator[Any]):
    def __init__(self, events: Iterable[Any]) -> None:
        self._events = iter(events)
        self.closed = False

    def __iter__(self) -> FakeStream:
        return self

    def __next__(self) -> Any:
        return next(self._events)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def llm(mocker) -> OpenAILargeLanguageModel:
    instance = object.__new__(OpenAILargeLanguageModel)
    instance._calc_response_usage = mocker.Mock(return_value=LLMUsage.empty_usage())
    return instance


@pytest.fixture
def prompt_messages() -> list[UserPromptMessage]:
    return [UserPromptMessage(content="Hello")]


@pytest.fixture
def response_factory() -> Callable[..., SimpleNamespace]:
    def make(
        *,
        output: list[Any] | None = None,
        output_text: str = "",
        status: str | None = "completed",
        usage: Any = _DEFAULT_USAGE,
        error: Any = None,
        incomplete_reason: str | None = None,
        model: str = "gpt-5.6",
    ) -> SimpleNamespace:
        if usage is _DEFAULT_USAGE:
            usage = SimpleNamespace(input_tokens=11, output_tokens=7)
        return SimpleNamespace(
            id="resp_1",
            model=model,
            output=[] if output is None else output,
            output_text=output_text,
            status=status,
            usage=usage,
            error=error,
            incomplete_details=(
                SimpleNamespace(reason=incomplete_reason)
                if incomplete_reason is not None
                else None
            ),
        )

    return make


@pytest.fixture
def invoke_stream(llm, mocker, prompt_messages):
    def invoke(
        events: Iterable[Any],
        *,
        stop: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> tuple[list[Any], FakeStream, Any]:
        fake = FakeStream(events)
        client = mocker.Mock()
        client.responses.create.return_value = fake
        chunks = list(
            response_stream.generate(
                llm,
                client,
                "gpt-5.6",
                {},
                prompt_messages,
                parameters or {},
                None,
                stop,
                None,
            )
        )
        return chunks, fake, client

    return invoke


@pytest.fixture
def fake_stream_factory() -> Callable[[Iterable[Any]], FakeStream]:
    return FakeStream
