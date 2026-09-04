"""Unit tests for stream_mode_auth handling in _retry_with_safe_min_tokens.

validate_credentials() short-circuits to _retry_with_safe_min_tokens() for o1/o3/gpt-5
models, which skips the base implementation that reads `stream_mode_auth`. The helper has
to honour the credential itself, otherwise the setting is silently ignored for exactly the
models that take this path.
"""

from unittest.mock import MagicMock, patch

import pytest
from dify_plugin.errors.model import CredentialsValidateFailedError

from models.llm.llm import OpenAILargeLanguageModel

OPENAI_CLIENT = "models.llm.llm.OpenAI"

BASE_CREDENTIALS = {
    "endpoint_url": "https://api.example.com/v1/",
    "api_key": "test-key",
    "mode": "chat",
}


def _run(credentials, model="gpt-5.6-luna", stream_chunks=(MagicMock(),)):
    """Call _retry_with_safe_min_tokens with a stubbed OpenAI client and return the kwargs."""
    llm = OpenAILargeLanguageModel(model_schemas=[])
    stream = MagicMock()
    stream.__iter__ = lambda self: iter(stream_chunks)

    with patch(OPENAI_CLIENT) as client_cls:
        client_cls.return_value.chat.completions.create.return_value = stream
        client_cls.return_value.completions.create.return_value = stream
        llm._retry_with_safe_min_tokens(model, credentials)
        create = client_cls.return_value.chat.completions.create
        if not create.called:
            create = client_cls.return_value.completions.create
        return create.call_args.kwargs, stream


def test_stream_mode_auth_use_validates_with_streaming():
    kwargs, stream = _run({**BASE_CREDENTIALS, "stream_mode_auth": "use"})

    assert kwargs["stream"] is True
    # The stream must be consumed and released, not handed back unread.
    stream.close.assert_called_once()


def test_stream_mode_auth_not_use_validates_without_streaming():
    kwargs, stream = _run({**BASE_CREDENTIALS, "stream_mode_auth": "not_use"})

    assert kwargs["stream"] is False
    stream.close.assert_not_called()


def test_stream_mode_auth_defaults_to_non_streaming():
    kwargs, _ = _run(BASE_CREDENTIALS)

    assert kwargs["stream"] is False


def test_completion_mode_also_honours_stream_mode_auth():
    kwargs, _ = _run({**BASE_CREDENTIALS, "mode": "completion", "stream_mode_auth": "use"})

    assert kwargs["stream"] is True


def test_streaming_failure_surfaces_as_validation_error():
    """An error raised while reading the stream must not escape as a raw exception."""
    llm = OpenAILargeLanguageModel(model_schemas=[])
    stream = MagicMock()

    def _boom(_self):
        raise RuntimeError("connection reset")

    stream.__iter__ = _boom

    with patch(OPENAI_CLIENT) as client_cls:
        client_cls.return_value.chat.completions.create.return_value = stream
        with pytest.raises(CredentialsValidateFailedError):
            llm._retry_with_safe_min_tokens(
                "gpt-5.6-luna", {**BASE_CREDENTIALS, "stream_mode_auth": "use"}
            )

    stream.close.assert_called_once()
