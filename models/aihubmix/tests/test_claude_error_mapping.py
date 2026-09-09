from pathlib import Path

import anthropic
import httpx
import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import UserPromptMessage
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

from models.llm import anthropic as anthropic_module
from models.llm.llm import AihubmixLargeLanguageModel

MODEL = "claude-opus-5"
SCHEMA_PATH = Path(__file__).parents[1] / "models" / "llm" / f"{MODEL}.yaml"
REQUEST = httpx.Request("POST", "https://example.invalid/v1/messages")


def _status_error(cls: type[anthropic.APIStatusError], status_code: int) -> anthropic.APIStatusError:
    response = httpx.Response(status_code, request=REQUEST)
    return cls(f"Error code: {status_code}", response=response, body=None)


def _invoke_raising(monkeypatch, error: Exception) -> None:
    class _Messages:
        def create(self, **kwargs):
            raise error

    class _Anthropic:
        def __init__(self, **kwargs) -> None:
            self.messages = _Messages()

    monkeypatch.setattr(anthropic_module, "Anthropic", _Anthropic)

    schemas = [AIModelEntity.model_validate(yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8")))]
    llm = AihubmixLargeLanguageModel(schemas)
    with llm.timing_context():
        llm._invoke(
            model=MODEL,
            credentials={"api_key": "fake-key-for-test", "api_url": "https://example.invalid"},
            prompt_messages=[UserPromptMessage(content="Hello")],
            model_parameters={"max_tokens": 64, "thinking": False, "effort": "high"},
            stream=False,
        )


@pytest.mark.parametrize(
    ("upstream_error", "expected"),
    [
        (_status_error(anthropic.AuthenticationError, 401), InvokeAuthorizationError),
        (_status_error(anthropic.RateLimitError, 429), InvokeRateLimitError),
        (_status_error(anthropic.BadRequestError, 400), InvokeBadRequestError),
        (_status_error(anthropic.InternalServerError, 500), InvokeServerUnavailableError),
    ],
    ids=["401", "429", "400", "500"],
)
def test_claude_upstream_errors_map_to_specific_invoke_errors(monkeypatch, upstream_error, expected) -> None:
    with pytest.raises(expected):
        _invoke_raising(monkeypatch, upstream_error)


def test_claude_connection_error_maps_to_invoke_connection_error(monkeypatch) -> None:
    with pytest.raises(InvokeConnectionError):
        _invoke_raising(monkeypatch, anthropic.APIConnectionError(request=REQUEST))
