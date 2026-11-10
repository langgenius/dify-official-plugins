"""Regression tests for the speech2text `language` and `initial_prompt` handling.

The plugin used to force both fields into every transcription request:
`language` fell back to a hardcoded value and the credential schema only
offered `zh`, `en`, `ja` and `ko`, while `prompt` fell back to the literal
string "convert the audio to text". Both are optional in the OpenAI
transcription API, so an OpenAI-compatible server that serves any other
language could not be used at all, and the injected decoder prompt biased
the transcript.

These tests drive the model directly so we can capture the form payload the
implementation actually sends, without needing a real transcription server.
"""

import io
from unittest.mock import MagicMock, patch

from models.speech2text.speech2text import OpenAISpeech2TextModel


def _captured_payload(mock_post):
    """Extract the form data passed to requests.post from the mock call."""
    assert mock_post.call_count == 1
    _args, kwargs = mock_post.call_args
    return kwargs.get("data") or {}


def _credentials(**overrides):
    creds = {
        "endpoint_url": "https://asr.example.com/v1",
        "api_key": "",
        "endpoint_model_name": "whisper-1",
    }
    creds.update(overrides)
    return creds


def _invoke(credentials):
    model = OpenAISpeech2TextModel(model_schemas=[])
    with patch("models.speech2text.speech2text.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"text": "ok"})
        model._invoke(
            model="whisper-1",
            credentials=credentials,
            file=io.BytesIO(b"RIFF"),
        )
    return mock_post


def test_language_is_omitted_when_not_configured():
    payload = _captured_payload(_invoke(_credentials()))
    assert "language" not in payload, (
        f"An unconfigured language must let the server auto-detect; payload={payload!r}"
    )


def test_prompt_is_omitted_when_not_configured():
    payload = _captured_payload(_invoke(_credentials()))
    assert "prompt" not in payload, (
        f"An unconfigured initial prompt must not bias the transcript; payload={payload!r}"
    )


def test_language_outside_the_former_option_list_is_forwarded():
    payload = _captured_payload(_invoke(_credentials(language="ru")))
    assert payload.get("language") == "ru", (
        f"Any ISO-639-1 code must reach the server, not just zh/en/ja/ko; payload={payload!r}"
    )


def test_configured_prompt_is_forwarded():
    payload = _captured_payload(_invoke(_credentials(initial_prompt="Kubernetes, kubectl")))
    assert payload.get("prompt") == "Kubernetes, kubectl", (
        f"A configured initial prompt must reach the server; payload={payload!r}"
    )


def test_request_has_a_timeout():
    mock_post = _invoke(_credentials())
    _args, kwargs = mock_post.call_args
    assert kwargs.get("timeout") is not None, (
        "A stalled transcription server must not hang the worker thread forever"
    )
