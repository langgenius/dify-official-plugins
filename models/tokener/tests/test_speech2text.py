import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
from dify_plugin.config.config import DifyPluginEnv
from dify_plugin.core.plugin_registration import PluginRegistration
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

MODELS = [
    "whisper-1",
    "gpt-4o-mini-transcribe",
    "gpt-4o-mini-transcribe-2025-12-15",
    "gpt-4o-transcribe",
    "gpt-4o-transcribe-diarize",
]


def speech2text_model():
    import yaml
    from dify_plugin.entities.model import AIModelEntity
    from test_speech2text_catalog import catalog

    from scripts.sync_catalog import render_catalog

    model = PluginRegistration(DifyPluginEnv()).get_model_instance("tokener", ModelType.SPEECH2TEXT)
    files = render_catalog(catalog(), model_type="speech2text")
    model.model_schemas = [
        AIModelEntity.model_validate(yaml.safe_load(content))
        for name, content in files.items()
        if name != "_position.yaml"
    ]
    return model


def response(body, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body).encode()
    result._content_consumed = True
    return result


@pytest.mark.parametrize("model_id", MODELS)
def test_speech2text_fixture_public_invoke_preserves_model_and_multipart(model_id):
    model = speech2text_model()
    assert {schema.model for schema in model.model_schemas} == set(MODELS)
    audio = io.BytesIO(b"audio bytes")
    audio.name = "recording.wav"
    credentials = {"api_key": "test", "endpoint_model_name": "wrong", "endpoint_url": "wrong"}
    expected = {"model": model_id}
    if model_id == "gpt-4o-transcribe-diarize":
        expected |= {"chunking_strategy": "auto", "response_format": "diarized_json"}
    with patch("requests.post", return_value=response({"text": "transcribed"})) as post:
        assert model.invoke(model_id, credentials, audio, user="user") == "transcribed"
    assert post.call_args.args == ("https://api.tokener.ai/v1/audio/transcriptions",)
    assert post.call_args.kwargs["data"] == expected
    assert post.call_args.kwargs["files"] == [("file", audio)]
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer test"}
    assert "json" not in post.call_args.kwargs
    assert post.call_count == 1
    assert audio.closed
    assert credentials["endpoint_model_name"] == "wrong"


def test_speech2text_diarized_json_returns_source_plugin_text():
    body = json.loads(Path("tests/fixtures/diarized_transcription.json").read_text())
    with patch("requests.post", return_value=response(body)):
        result = speech2text_model().invoke(
            "gpt-4o-transcribe-diarize", {"api_key": "test"}, io.BytesIO(b"audio")
        )
    assert result == body["text"] == "Hello. Good morning."


@pytest.mark.parametrize(
    "status,error",
    [
        (400, InvokeBadRequestError),
        (401, InvokeAuthorizationError),
        (403, InvokeAuthorizationError),
        (429, InvokeRateLimitError),
        (503, InvokeServerUnavailableError),
    ],
)
def test_speech2text_http_failure_closes_upload_and_response(status, error):
    audio = io.BytesIO(b"audio")
    reply = response({"error": "private upstream detail"}, status)
    with (
        patch("requests.post", return_value=reply),
        patch.object(reply, "close", wraps=reply.close) as close,
        pytest.raises(error) as caught,
    ):
        speech2text_model().invoke("whisper-1", {"api_key": "test"}, audio)
    assert audio.closed
    close.assert_called_once()
    assert "private upstream detail" not in str(caught.value)


@pytest.mark.parametrize("body", [{}, {"text": None}, {"text": ["invalid"]}, []])
def test_speech2text_rejects_invalid_transcription(body):
    audio = io.BytesIO(b"audio")
    with (
        patch("requests.post", return_value=response(body)),
        pytest.raises(InvokeServerUnavailableError),
    ):
        speech2text_model().invoke("whisper-1", {"api_key": "test"}, audio)
    assert audio.closed


def test_speech2text_invalid_json_closes_upload():
    reply = response({})
    reply._content = b"not json"
    audio = io.BytesIO(b"audio")
    with (
        patch("requests.post", return_value=reply),
        pytest.raises(InvokeServerUnavailableError),
    ):
        speech2text_model().invoke("whisper-1", {"api_key": "test"}, audio)
    assert audio.closed


def test_speech2text_network_failure_does_not_retry_or_leak_details():
    audio = io.BytesIO(b"audio")
    with (
        patch("requests.post", side_effect=requests.Timeout("private detail")) as post,
        pytest.raises(InvokeConnectionError) as caught,
    ):
        speech2text_model().invoke("whisper-1", {"api_key": "test"}, audio)
    assert audio.closed
    assert post.call_count == 1
    assert "private detail" not in str(caught.value)


def test_speech2text_validation_closes_demo_file_on_failure():
    model = speech2text_model()
    demo = io.BytesIO(b"demo audio")
    with (
        patch("builtins.open", return_value=demo) as open_file,
        patch("requests.post", return_value=response({}, 403)),
        pytest.raises(CredentialsValidateFailedError),
    ):
        model.validate_credentials("gpt-4o-transcribe-diarize", {"api_key": "test"})
    open_file.assert_called_once_with(model._get_demo_file_path(), "rb")
    assert demo.closed


def test_speech2text_multipart_wire_request():
    from email import policy
    from email.parser import BytesParser

    audio = io.BytesIO(b"binary\x00audio\xff")
    audio.name = "recording.wav"
    with patch("requests.sessions.Session.send", return_value=response({"text": "ok"})) as send:
        assert (
            speech2text_model().invoke("gpt-4o-transcribe-diarize", {"api_key": "test"}, audio)
            == "ok"
        )
    request = send.call_args.args[0]
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {request.headers['Content-Type']}\r\n\r\n".encode() + request.body
    )
    parts = {
        part.get_param("name", header="content-disposition"): part for part in message.iter_parts()
    }
    assert set(parts) == {"model", "file", "chunking_strategy", "response_format"}
    assert parts["file"].get_payload(decode=True) == b"binary\x00audio\xff"
    assert parts["file"].get_filename() == "recording.wav"
    assert parts["model"].get_payload() == "gpt-4o-transcribe-diarize"
    assert parts["chunking_strategy"].get_payload() == "auto"
    assert parts["response_format"].get_payload() == "diarized_json"
    assert request.method == "POST"
    assert request.url == "https://api.tokener.ai/v1/audio/transcriptions"
    assert audio.closed
