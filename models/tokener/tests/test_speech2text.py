import io
import json
from pathlib import Path
from unittest.mock import patch

import requests
from dify_plugin.config.config import DifyPluginEnv
from dify_plugin.core.plugin_registration import PluginRegistration
from dify_plugin.entities.model import ModelType

from models._credentials import ENDPOINT_URL


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


def test_speech2text_diarized_json_returns_source_plugin_text():
    body = json.loads(Path("tests/fixtures/diarized_transcription.json").read_text())
    with patch("requests.post", return_value=response(body)):
        result = speech2text_model().invoke(
            "gpt-4o-transcribe-diarize", {"api_key": "test"}, io.BytesIO(b"audio")
        )
    assert result == body["text"] == "Hello. Good morning."


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
    assert request.url == f"{ENDPOINT_URL}/audio/transcriptions"
    assert audio.closed


def test_speech2text_credentials_accept_a_successful_demo_transcription():
    model = speech2text_model()
    with patch("requests.post", return_value=response({"text": "ok"})):
        model.validate_credentials("gpt-4o-transcribe-diarize", {"api_key": "test"})
