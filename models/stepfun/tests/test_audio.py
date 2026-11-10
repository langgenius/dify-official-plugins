import base64
import io
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from models.speech2text.speech2text import StepfunSpeech2TextModel
from models.tts.tts import StepfunText2SpeechModel

ROOT = Path(__file__).resolve().parents[1]
CREDS = {"api_key": "test-key"}
WAV = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"audio"


def response(events=None, chunks=None, status=200):
    result = Mock(status_code=status, headers={"Content-Type": "audio/mpeg"})
    result.__enter__ = Mock(return_value=result)

    def close_response(*args):
        result.close()
        return False

    result.__exit__ = Mock(side_effect=close_response)
    result.iter_content.return_value = chunks if chunks is not None else [b"mp3-a", b"", b"mp3-b"]
    result.iter_lines.return_value = [
        ": keepalive",
        "",
        *[line for event in (events or []) for line in ["data: " + json.dumps(event), ""]],
    ]
    return result


@pytest.fixture
def tts():
    model = StepfunText2SpeechModel([])
    schema = AIModelEntity.model_validate(
        yaml.safe_load((ROOT / "models/tts/stepaudio-3-tts.yaml").read_text())
    )
    model.get_model_schema = Mock(return_value=schema)
    return model


@pytest.fixture
def asr():
    return StepfunSpeech2TextModel([])


@pytest.mark.parametrize(
    "international,host", [("false", "api.stepfun.com"), ("true", "api.stepfun.ai")]
)
def test_tts_request_and_voice_fallback(tts, international, host):
    reply = response()
    with patch("requests.post", return_value=reply) as post:
        audio = b"".join(
            tts._invoke(
                "stepaudio-3-tts",
                "",
                {**CREDS, "use_international_endpoint": international},
                "你好",
                "invalid",
            )
        )
    assert audio == b"mp3-amp3-b"
    assert post.call_args.args[0] == f"https://{host}/v1/audio/speech"
    assert post.call_args.kwargs["json"] == {
        "model": "stepaudio-3-tts",
        "input": "你好",
        "voice": "cixingnansheng",
        "response_format": "mp3",
        "stream_format": "audio",
    }
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert "X-Dify-App-Id" not in post.call_args.kwargs["headers"]
    reply.close.assert_called_once()


def test_tts_long_text_preserves_input_and_valid_voice(tts):
    text = "你好。" + "文" * 2500
    with patch("requests.post", side_effect=lambda *a, **kw: response()) as post:
        list(tts._invoke("stepaudio-3-tts", "", CREDS, text, "wenrounansheng"))
    inputs = [call.kwargs["json"]["input"] for call in post.call_args_list]
    assert "".join(inputs) == text
    assert all(0 < len(chunk) <= 1000 for chunk in inputs)
    assert all(call.kwargs["json"]["voice"] == "wenrounansheng" for call in post.call_args_list)


def test_empty_text_is_rejected_before_request(tts):
    with patch("requests.post") as post, pytest.raises(InvokeBadRequestError):
        tts._invoke("stepaudio-3-tts", "", CREDS, "  ", "")
    post.assert_not_called()


@pytest.mark.parametrize(
    "status,error",
    [
        (401, InvokeAuthorizationError),
        (403, InvokeAuthorizationError),
        (429, InvokeRateLimitError),
        (500, InvokeServerUnavailableError),
        (400, InvokeBadRequestError),
    ],
)
def test_http_errors_during_iteration(tts, status, error):
    reply = response(status=status)
    with patch("requests.post", return_value=reply), pytest.raises(error):
        list(tts._invoke("stepaudio-3-tts", "", CREDS, "hello", ""))
    reply.close.assert_called_once()


def test_stream_timeout_is_mapped_and_closed(tts):
    reply = response()
    reply.iter_content.side_effect = requests.Timeout("timeout")
    with patch("requests.post", return_value=reply), pytest.raises(InvokeConnectionError):
        list(tts._invoke("stepaudio-3-tts", "", CREDS, "hello", ""))
    reply.close.assert_called_once()


def test_empty_audio_rejected(tts):
    with (
        patch("requests.post", return_value=response(chunks=[])),
        pytest.raises(InvokeServerUnavailableError),
    ):
        list(tts._invoke("stepaudio-3-tts", "", CREDS, "hello", ""))


def test_tts_validation_consumes_stream(tts):
    with (
        patch("requests.post", return_value=response(status=401)),
        pytest.raises(CredentialsValidateFailedError),
    ):
        tts.validate_credentials("stepaudio-3-tts", CREDS)
    with patch("requests.post", return_value=response()) as post:
        tts.validate_credentials("stepaudio-3-tts", CREDS)
    post.assert_called_once()


def test_asr_returns_final_text_without_duplicate_deltas(asr):
    reply = response(
        events=[
            {"type": "transcript.text.delta", "delta": "错字"},
            {"type": "transcript.text.done", "text": "正确的转写"},
        ]
    )
    with patch("requests.post", return_value=reply) as post:
        result = asr._invoke("stepaudio-3-asr-max", CREDS, io.BytesIO(WAV))
    assert result == "正确的转写"
    assert post.call_args.args[0] == "https://api.stepfun.com/v1/audio/asr/sse"
    payload = post.call_args.kwargs["json"]["audio"]
    assert base64.b64decode(payload["data"]) == WAV
    assert payload["input"] == {
        "transcription": {"model": "stepaudio-3-asr-max", "enable_itn": True},
        "format": {"type": "wav"},
    }
    assert post.call_args.kwargs["headers"]["Accept"] == "text/event-stream"
    reply.close.assert_called_once()


@pytest.mark.parametrize(
    "data,container",
    [
        (WAV, "wav"),
        (b"OggSxx", "ogg"),
        (b"ID3xx", "mp3"),
        (b"\xff\xfbxx", "mp3"),
        (b"\x00\x00\x00\x18ftypM4A ", "m4a"),
    ],
)
def test_asr_unnamed_file_formats(asr, data, container):
    assert asr._audio_format(data) == container


@pytest.mark.parametrize("data", [b"", b"random", b"\xff\xf1aac", b"fLaCxx"])
def test_asr_invalid_input(asr, data):
    with patch("requests.post") as post, pytest.raises(InvokeBadRequestError):
        asr._invoke("stepaudio-3-asr-max", CREDS, io.BytesIO(data))
    post.assert_not_called()


def test_asr_size_limit(asr):
    asr._MAX_BYTES = 12
    with pytest.raises(InvokeBadRequestError):
        asr._invoke("stepaudio-3-asr-max", CREDS, io.BytesIO(WAV))


@pytest.mark.parametrize(
    "events",
    [
        [{"type": "error", "message": "failed"}],
        [{"type": "transcript.text.delta", "delta": "partial"}],
        [{"type": "transcript.text.done", "text": None}],
    ],
)
def test_asr_incomplete_or_error_response(asr, events):
    reply = response(events=events)
    with patch("requests.post", return_value=reply), pytest.raises(InvokeServerUnavailableError):
        asr._invoke("stepaudio-3-asr-max", CREDS, io.BytesIO(WAV))
    reply.close.assert_called_once()


def test_asr_silence_is_valid(asr):
    with patch(
        "requests.post",
        return_value=response(events=[{"type": "transcript.text.done", "text": ""}]),
    ):
        assert asr._invoke("stepaudio-3-asr-max", CREDS, io.BytesIO(WAV)) == ""


def test_asr_validation_uses_sdk_demo(asr):
    with patch(
        "requests.post",
        return_value=response(events=[{"type": "transcript.text.done", "text": "hello"}]),
    ) as post:
        asr.validate_credentials("stepaudio-3-asr-max", CREDS)
    assert post.call_args.kwargs["json"]["audio"]["input"]["format"]["type"] == "mp3"


def test_sse_multiline_and_done(asr):
    reply = response()
    reply.iter_lines.return_value = [
        ": ping",
        "event: transcript.text.done",
        'data: {"type":"transcript.text.done",',
        'data: "text":"你好"}',
        "",
        "data: [DONE]",
        "",
    ]
    assert list(asr._events(reply)) == [{"type": "transcript.text.done", "text": "你好"}]


def test_audio_registered_and_schemas_valid():
    provider = yaml.safe_load((ROOT / "provider/stepfun.yaml").read_text())
    manifest = yaml.safe_load((ROOT / "manifest.yaml").read_text())
    for kind, name in [("tts", "stepaudio-3-tts"), ("speech2text", "stepaudio-3-asr-max")]:
        assert kind in provider["supported_model_types"]
        assert f"models/{kind}/{kind}.py" in provider["extra"]["python"]["model_sources"]
        assert manifest["resource"]["permission"]["model"][kind] is True
        assert (
            AIModelEntity.model_validate(
                yaml.safe_load((ROOT / f"models/{kind}/{name}.yaml").read_text())
            ).model
            == name
        )


def test_audio_metadata_opt_in(tts):
    with (
        patch("dify_plugin.get_current_session", return_value=Mock(app_id="app-test")),
        patch("requests.post", return_value=response()) as post,
    ):
        list(
            tts._invoke(
                "stepaudio-3-tts", "", {**CREDS, "enable_request_metadata": "enabled"}, "hello", ""
            )
        )
    assert post.call_args.kwargs["headers"]["X-Dify-App-Id"] == "app-test"


def test_tts_cancel_closes_response(tts):
    reply = response()
    with patch("requests.post", return_value=reply):
        stream = tts._invoke("stepaudio-3-tts", "", CREDS, "hello", "")
        assert next(stream) == b"mp3-a"
        stream.close()
    reply.close.assert_called_once()


def test_non_audio_success_response_rejected(tts):
    reply = response()
    reply.headers["Content-Type"] = "application/json"
    with patch("requests.post", return_value=reply), pytest.raises(InvokeServerUnavailableError):
        list(tts._invoke("stepaudio-3-tts", "", CREDS, "hello", ""))


def test_asr_international_and_http_authorization(asr):
    with (
        patch("requests.post", return_value=response(status=401)) as post,
        pytest.raises(InvokeAuthorizationError),
    ):
        asr.invoke(
            "stepaudio-3-asr-max", {**CREDS, "use_international_endpoint": "true"}, io.BytesIO(WAV)
        )
    assert post.call_args.args[0] == "https://api.stepfun.ai/v1/audio/asr/sse"
