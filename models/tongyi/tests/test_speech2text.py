import base64
import json
import os
import sys
from collections.abc import AsyncIterator
from io import BytesIO, StringIO
from unittest.mock import MagicMock, patch

import pytest
import requests
from dashscope.api_entities import dashscope_response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.speech2text.speech2text import TongyiSpeech2TextModel


def _model() -> TongyiSpeech2TextModel:
    return TongyiSpeech2TextModel(model_schemas=MagicMock())


def _named_bytes(data: bytes, name: str) -> BytesIO:
    file_obj = BytesIO(data)
    file_obj.name = name
    return file_obj


def _wav_file() -> BytesIO:
    return _named_bytes(b"RIFF\x24\x00\x00\x00WAVE" + b"\x00" * 16, "audio.wav")


def _run_worker_main(monkeypatch, payload: dict) -> tuple[int, str, str]:
    from models.speech2text import _stt_worker

    stdout = StringIO()
    stderr = StringIO()
    monkeypatch.setattr(sys, "stdin", StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    return _stt_worker.main(), stdout.getvalue(), stderr.getvalue()


def _worker_payload() -> dict:
    return {
        "file_path": "/tmp/audio.wav",
        "model": "paraformer-realtime-v1",
        "audio_format": "wav",
        "sample_rate": 16000,
        "api_key": "test-key",
        "base_address": None,
        "headers": {},
    }


def _http_response(data: dict | str, status_code: int = 200) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response._content = (data if isinstance(data, str) else json.dumps(data)).encode()
    response.headers["Content-Type"] = "application/json"
    return response


def _sdk_response(
    output: dict | None, request_id: str = "request-id"
) -> dashscope_response.TranscriptionResponse:
    output = {"task_id": "task-1", "task_status": "SUCCEEDED", **(output or {})}
    return dashscope_response.TranscriptionResponse.from_api_response(
        dashscope_response.DashScopeAPIResponse(
            status_code=200, request_id=request_id, output=output, headers={}
        )
    )


def test_get_audio_type_prefers_magic_bytes_without_decoding() -> None:
    file_obj = _named_bytes(b"RIFF\x24\x00\x00\x00WAVE" + b"\x00" * 16, "temp.mp3")
    file_obj.seek(5)

    with patch(
        "models.speech2text.speech2text.AudioSegment.from_file",
        side_effect=AssertionError("magic-byte detection should not decode audio"),
    ) as decode_mock:
        assert _model().get_audio_type(file_obj) == "wav"

    decode_mock.assert_not_called()
    assert file_obj.tell() == 5


@pytest.mark.parametrize(
    ("data", "name", "expected"),
    [
        (b"ID3" + b"\0" * 40, "upload.wav", "mp3"),
        (b"\0\0\0\x18ftypM4A " + b"\0" * 12, "upload.wav", "m4a"),
        (b"\0\0\0\x01ftyp" + b"\0" * 7 + b"\x18M4A " + b"\0" * 4, "upload.wav", "m4a"),
        (b"\0\0\0\x18ftypisom" + b"\0" * 12, "upload.wav", "mp4"),
        (b"\0\0\0\x18ftypisom" + b"\0" * 12, "upload.m4a", "m4a"),
        (b"\0\0\0\x18ftypqt  " + b"\0" * 12, "upload.wav", "mov"),
        (b"\x1a\x45\xdf\xa3\x87\x42\x82\x84webm", "upload.wav", "webm"),
        (b"\x1a\x45\xdf\xa3\x8b\x42\x82\x88matroska", "upload.wav", "mkv"),
        (b"OggS" + b"\0" * 22 + b"\x01\x08OpusHead", "upload.wav", "opus"),
        (b"OggS" + b"\0" * 22 + b"\x01\x07\x01vorbis", "upload.wav", "ogg"),
    ],
)
def test_get_audio_type_uses_container_metadata_before_filename(
    data: bytes, name: str, expected: str
) -> None:
    file_obj = _named_bytes(data, name)

    with patch(
        "models.speech2text.speech2text.AudioSegment.from_file",
        side_effect=AssertionError("magic-byte detection should not decode audio"),
    ):
        assert _model().get_audio_type(file_obj) == expected


def test_invoke_reuses_detected_audio_format_for_decoding() -> None:
    file_obj = _named_bytes(b"RIFF\x24\x00\x00\x00WAVE" + b"\x00" * 16, "upload.mp3")
    audio = MagicMock(frame_rate=16000)
    result = MagicMock()
    result.status_code = 200
    result.get_sentence.return_value = [{"text": "hello"}]
    recognition = MagicMock()
    recognition.call.return_value = result

    with patch.dict(os.environ, {"TONGYI_STT_SUBPROCESS": "false"}):
        with patch(
            "models.speech2text.speech2text.AudioSegment.from_file", return_value=audio
        ) as decode_mock:
            with patch("models.speech2text.speech2text.Recognition", return_value=recognition):
                assert (
                    _model()._invoke(
                        model="paraformer-realtime-v1",
                        credentials={"dashscope_api_key": "test-key"},
                        file=file_obj,
                    )
                    == "hello"
                )

    decode_mock.assert_called_once()
    assert decode_mock.call_args.kwargs["format"] == "wav"


def test_invoke_normalizes_non_dict_sentences() -> None:
    file_obj = _named_bytes(b"RIFF\x24\x00\x00\x00WAVE" + b"\x00" * 16, "upload.wav")
    audio = MagicMock(frame_rate=16000)
    result = MagicMock()
    result.status_code = 200
    result.get_sentence.return_value = ["hello", {"text": "world"}]
    recognition = MagicMock()
    recognition.call.return_value = result

    with patch.dict(os.environ, {"TONGYI_STT_SUBPROCESS": "false"}):
        with patch("models.speech2text.speech2text.AudioSegment.from_file", return_value=audio):
            with patch("models.speech2text.speech2text.Recognition", return_value=recognition):
                assert (
                    _model()._invoke(
                        model="paraformer-realtime-v1",
                        credentials={"dashscope_api_key": "test-key"},
                        file=file_obj,
                    )
                    == "hello\nworld"
                )


def test_invoke_raises_dashscope_status_error() -> None:
    result = MagicMock(
        status_code=400,
        code="InvalidModel",
        message="Model not available in this region",
        request_id="request-1",
    )
    recognition = MagicMock()
    recognition.call.return_value = result

    with (
        patch.dict(os.environ, {"TONGYI_STT_SUBPROCESS": "false"}),
        patch(
            "models.speech2text.speech2text.AudioSegment.from_file",
            return_value=MagicMock(frame_rate=16000),
        ),
        patch("models.speech2text.speech2text.Recognition", return_value=recognition),
        patch("models.speech2text.speech2text._patch_dashscope_async_bridge_for_gevent"),
        pytest.raises(ValueError) as exc_info,
    ):
        _model()._invoke(
            model="paraformer-realtime-v1",
            credentials={"dashscope_api_key": "test-key"},
            file=_wav_file(),
        )

    message = str(exc_info.value)
    assert "status: 400" in message
    assert "Model not available in this region" in message
    assert "InvalidModel" in message
    assert "request-1" in message
    result.get_sentence.assert_not_called()


def test_invoke_fun_asr_flash_uses_http_base64() -> None:
    response = _http_response({"output": {"text": "hello flash"}})
    audio_file = _wav_file()
    audio_bytes = audio_file.getvalue()

    with patch("models.speech2text.speech2text.requests.post", return_value=response) as post:
        text = _model()._invoke(
            model="fun-asr-flash-2026-06-15",
            credentials={"dashscope_api_key": "test-key", "use_international_endpoint": "true"},
            file=audio_file,
        )

    assert text == "hello flash"
    assert (
        post.call_args.args[0]
        == "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    )
    payload = post.call_args.kwargs["json"]
    headers = post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer test-key"
    assert headers["X-DashScope-SSE"] == "disable"
    assert payload["model"] == "fun-asr-flash-2026-06-15"
    assert payload["parameters"] == {"format": "wav"}
    assert payload["input"]["messages"][0]["role"] == "user"
    assert payload["input"]["messages"][0]["content"][0]["type"] == "input_audio"
    data_uri = payload["input"]["messages"][0]["content"][0]["input_audio"]["data"]
    prefix, encoded = data_uri.split(",", 1)
    assert prefix == "data:audio/wav;base64"
    assert base64.b64decode(encoded) == audio_bytes
    assert post.call_args.kwargs["timeout"] == (10, 600)


def test_invoke_fun_asr_flash_preserves_http_error() -> None:
    response = _http_response(
        {
            "code": "InvalidParameter",
            "message": "The audio format is invalid.",
            "request_id": "request-flash-error",
        },
        status_code=400,
    )

    with (
        patch("models.speech2text.speech2text.requests.post", return_value=response),
        pytest.raises(ValueError) as exc_info,
    ):
        _model()._invoke(
            model="fun-asr-flash-2026-06-15",
            credentials={"dashscope_api_key": "test-key"},
            file=_wav_file(),
        )

    error = str(exc_info.value)
    assert "status: 400" in error
    assert "InvalidParameter" in error
    assert "The audio format is invalid." in error
    assert "request-flash-error" in error


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (_http_response("upstream failure", status_code=502), "InvalidJSONResponse"),
        (_http_response({"output": {}}), "missing output.text"),
    ],
)
def test_invoke_fun_asr_flash_rejects_malformed_responses(
    response: requests.Response, expected: str
) -> None:
    with (
        patch("models.speech2text.speech2text.requests.post", return_value=response),
        pytest.raises(ValueError, match=expected),
    ):
        _model()._invoke(
            model="fun-asr-flash-2026-06-15",
            credentials={"dashscope_api_key": "test-key"},
            file=_wav_file(),
        )


def test_invoke_fun_asr_flash_validates_7_mib_boundary_before_encoding() -> None:
    header = b"RIFF\x24\x00\x00\x00WAVE"
    limit = 7 * 1024 * 1024
    oversized = _named_bytes(header + b"\0" * (limit + 1 - len(header)), "large.wav")

    with (
        patch(
            "models.speech2text.speech2text.Path.read_bytes",
            side_effect=AssertionError("oversized audio must not be read for encoding"),
        ) as read_bytes,
        patch(
            "models.speech2text.speech2text.base64.b64encode",
            side_effect=AssertionError("oversized audio must not be encoded"),
        ) as encode,
        patch("models.speech2text.speech2text.requests.post") as post,
        pytest.raises(ValueError, match="must not exceed 7 MB"),
    ):
        _model()._invoke(
            model="fun-asr-flash-2026-06-15",
            credentials={"dashscope_api_key": "test-key"},
            file=oversized,
        )

    read_bytes.assert_not_called()
    encode.assert_not_called()
    post.assert_not_called()

    allowed = _named_bytes(header + b"\0" * (limit - len(header)), "maximum.wav")
    response = _http_response({"output": {"text": "accepted"}})
    with (
        patch(
            "models.speech2text.speech2text.Path.read_bytes", return_value=b"audio"
        ) as read_bytes,
        patch("models.speech2text.speech2text.requests.post", return_value=response),
    ):
        assert (
            _model()._invoke(
                model="fun-asr-flash-2026-06-15",
                credentials={"dashscope_api_key": "test-key"},
                file=allowed,
            )
            == "accepted"
        )

    read_bytes.assert_called_once()


def test_invoke_preserves_http_transport_errors() -> None:
    error = requests.exceptions.ReadTimeout("timed out")
    with (
        patch("models.speech2text.speech2text.requests.post", side_effect=error),
        pytest.raises(requests.exceptions.ReadTimeout) as exc_info,
    ):
        _model()._invoke(
            model="fun-asr-flash-2026-06-15",
            credentials={"dashscope_api_key": "test-key"},
            file=_wav_file(),
        )

    assert exc_info.value is error


def test_invoke_fun_asr_uploads_waits_and_downloads() -> None:
    submit_response = _http_response(
        {"output": {"task_id": "task-1", "task_status": "PENDING"}, "request_id": "submit-request"}
    )
    task_response = _sdk_response(
        {
            "results": [
                {
                    "subtask_status": "SUCCEEDED",
                    "transcription_url": "https://example.com/result.json",
                }
            ]
        }
    )
    unavailable_response = _http_response(
        {"code": "ServiceUnavailable", "message": "try again"}, status_code=503
    )
    transcription_response = _http_response({"transcripts": [{"text": "hello"}, {"text": "world"}]})

    with (
        patch(
            "models.speech2text.speech2text.OssUtils.upload",
            return_value=("oss://temporary/audio.wav", {}),
        ) as upload,
        patch("models.speech2text.speech2text.requests.post", return_value=submit_response) as post,
        patch(
            "models.speech2text.speech2text.Transcription.wait",
            side_effect=[requests.exceptions.ReadTimeout("poll timed out"), task_response],
        ) as wait,
        patch(
            "models.speech2text.speech2text.requests.get",
            side_effect=[unavailable_response, unavailable_response, transcription_response],
        ) as get,
        patch("models.speech2text.speech2text.time.sleep") as sleep,
        patch("models.speech2text.speech2text.time.monotonic", return_value=0),
    ):
        text = _model()._invoke(
            model="fun-asr",
            credentials={"dashscope_api_key": "test-key", "use_international_endpoint": "true"},
            file=_wav_file(),
        )

    assert text == "hello\nworld"
    assert upload.call_args.kwargs["model"] == "fun-asr"
    assert upload.call_args.kwargs["api_key"] == "test-key"
    assert upload.call_args.kwargs["base_address"] == ("https://dashscope-intl.aliyuncs.com/api/v1")
    assert (
        post.call_args.args[0]
        == "https://dashscope-intl.aliyuncs.com/api/v1/services/audio/asr/transcription"
    )
    assert post.call_args.kwargs["json"] == {
        "model": "fun-asr",
        "input": {"file_urls": ["oss://temporary/audio.wav"]},
        "parameters": {},
    }
    submit_headers = post.call_args.kwargs["headers"]
    assert submit_headers["Authorization"] == "Bearer test-key"
    assert submit_headers["Content-Type"] == "application/json"
    assert submit_headers["X-DashScope-Async"] == "enable"
    assert submit_headers["X-DashScope-OssResourceResolve"] == "enable"
    assert post.call_args.kwargs["timeout"] == (10, 600)
    assert wait.call_args.args == ("task-1",)
    assert wait.call_args.kwargs["api_key"] == "test-key"
    assert wait.call_args.kwargs["base_address"] == "https://dashscope-intl.aliyuncs.com/api/v1"
    assert wait.call_args.kwargs["wait_timeout"] == 10_800
    upload.assert_called_once()
    post.assert_called_once()
    assert wait.call_count == 2
    assert get.call_count == 3
    assert all(call.args[0] == "https://example.com/result.json" for call in get.call_args_list)
    assert all(call.kwargs["timeout"] == (10, 600) for call in get.call_args_list)
    assert [call.args[0] for call in sleep.call_args_list] == [1, 1, 3]


@pytest.mark.parametrize(
    ("output", "request_id", "expected"),
    [
        (
            {
                "task_status": "SUCCEEDED",
                "results": [
                    {
                        "subtask_status": "FAILED",
                        "code": "InvalidFile.DownloadFailed",
                        "message": "The audio file cannot be downloaded.",
                    }
                ],
            },
            "request-4",
            ("InvalidFile.DownloadFailed", "The audio file cannot be downloaded."),
        ),
        (
            {
                "task_status": "FAILED",
                "code": "InternalError",
                "message": "The transcription task failed.",
            },
            "request-5",
            ("InternalError", "The transcription task failed."),
        ),
    ],
    ids=("subtask", "task"),
)
def test_invoke_fun_asr_preserves_errors(
    output: dict, request_id: str, expected: tuple[str, str]
) -> None:
    submit_response = _http_response(
        {
            "output": {"task_id": "task-error", "task_status": "PENDING"},
            "request_id": "submit-request",
        }
    )
    task_response = _sdk_response(output, request_id=request_id)
    with (
        patch(
            "models.speech2text.speech2text.OssUtils.upload",
            return_value=("oss://temporary/audio.wav", {}),
        ),
        patch("models.speech2text.speech2text.requests.post", return_value=submit_response),
        patch("models.speech2text.speech2text.Transcription.wait", return_value=task_response),
        pytest.raises(ValueError) as exc_info,
    ):
        _model()._invoke(
            model="fun-asr", credentials={"dashscope_api_key": "test-key"}, file=_wav_file()
        )

    message = str(exc_info.value)
    assert "status: FAILED" in message
    assert expected[0] in message
    assert expected[1] in message
    assert request_id in message


def test_invoke_patches_dashscope_async_bridge_by_default(monkeypatch) -> None:
    audio = MagicMock(frame_rate=16000)
    result = MagicMock()
    result.status_code = 200
    result.get_sentence.return_value = [{"text": "hello"}]
    recognition = MagicMock()
    recognition.call.return_value = result

    monkeypatch.delenv("TONGYI_STT_SUBPROCESS", raising=False)
    with patch("models.speech2text.speech2text.AudioSegment.from_file", return_value=audio):
        with patch("models.speech2text.speech2text.Recognition", return_value=recognition):
            with patch(
                "models.speech2text.speech2text._patch_dashscope_async_bridge_for_gevent"
            ) as patch_mock:
                with patch(
                    "models.speech2text.speech2text._run_recognition_in_subprocess",
                    side_effect=AssertionError("subprocess path should stay disabled"),
                ) as run_mock:
                    result_text = _model()._invoke(
                        model="paraformer-realtime-v1",
                        credentials={"dashscope_api_key": "test-key"},
                        file=_wav_file(),
                    )

    assert result_text == "hello"
    patch_mock.assert_called_once()
    run_mock.assert_not_called()


def test_dashscope_async_bridge_patch_yields_results() -> None:
    import dashscope.common.utils as dashscope_utils
    from models.speech2text import speech2text as st2

    async def stream() -> AsyncIterator[str]:
        yield "hello"
        yield "world"

    original_iter_over_async = dashscope_utils.iter_over_async
    original_flag = st2._DASHSCOPE_ASYNC_BRIDGE_PATCHED
    st2._DASHSCOPE_ASYNC_BRIDGE_PATCHED = False
    try:
        st2._patch_dashscope_async_bridge_for_gevent()

        assert list(dashscope_utils.iter_over_async(stream())) == ["hello", "world"]
    finally:
        dashscope_utils.iter_over_async = original_iter_over_async
        st2._DASHSCOPE_ASYNC_BRIDGE_PATCHED = original_flag


def test_invoke_uses_subprocess_when_env_is_true() -> None:
    from models.speech2text import speech2text as st2

    audio = MagicMock(frame_rate=16000)

    with patch.dict(os.environ, {"TONGYI_STT_SUBPROCESS": "1"}):
        with patch("models.speech2text.speech2text.AudioSegment.from_file", return_value=audio):
            with patch(
                "models.speech2text.speech2text._run_recognition_in_subprocess",
                return_value=("ok", [{"text": "hello"}, {"text": "world"}]),
            ) as run_mock:
                result = _model()._invoke(
                    model="paraformer-realtime-v1",
                    credentials={"dashscope_api_key": "test-key"},
                    file=_wav_file(),
                )

    assert result == "hello\nworld"
    run_mock.assert_called_once()
    _, _, audio_format, sample_rate, api_key, _, headers = run_mock.call_args.args
    assert audio_format == "wav"
    assert sample_rate == 16000
    assert api_key == "test-key"
    assert headers == dict(st2.BURY_POINT_HEADER)
    assert headers is not st2.BURY_POINT_HEADER


def test_invoke_raises_when_subprocess_returns_error() -> None:
    audio = MagicMock(frame_rate=16000)
    with patch.dict(os.environ, {"TONGYI_STT_SUBPROCESS": "1"}):
        with patch("models.speech2text.speech2text.AudioSegment.from_file", return_value=audio):
            with patch(
                "models.speech2text.speech2text._run_recognition_in_subprocess",
                return_value=("err", "recognition timeout"),
            ):
                try:
                    _model()._invoke(
                        model="paraformer-realtime-v1",
                        credentials={"dashscope_api_key": "test-key"},
                        file=_wav_file(),
                    )
                except ValueError as exc:
                    assert "recognition timeout" in str(exc)
                else:
                    raise AssertionError("expected subprocess error to raise ValueError")


def test_run_recognition_in_subprocess_returns_error_for_missing_file() -> None:
    from models.speech2text import speech2text as st2

    status, data = st2._run_recognition_in_subprocess(
        file_path="/missing/audio.wav",
        model="paraformer-realtime-v1",
        audio_format="wav",
        sample_rate=16000,
        api_key="test-key",
        base_address=None,
        headers={},
        timeout=30,
    )

    assert status == "err"
    assert isinstance(data, str)
    assert data


def test_worker_keeps_library_stdout_out_of_json(monkeypatch) -> None:
    from dashscope.audio import asr

    class FakeResult:
        status_code = 200

        def get_sentence(self):
            return [{"text": "hello"}]

    class FakeRecognition:
        def __init__(self, **kwargs):
            pass

        def call(self, **kwargs):
            print("dashscope library log")
            return FakeResult()

    monkeypatch.setattr(asr, "Recognition", FakeRecognition)

    exit_code, stdout, stderr = _run_worker_main(monkeypatch, _worker_payload())

    assert exit_code == 0
    assert json.loads(stdout) == {"status": "ok", "data": [{"text": "hello"}]}
    assert "dashscope library log" not in stdout
    assert "dashscope library log" in stderr


def test_worker_returns_dashscope_status_error(monkeypatch) -> None:
    from dashscope.audio import asr

    class FakeResult:
        status_code = 400
        code = "InvalidModel"
        message = "invalid audio"
        request_id = "request-1"

        def get_sentence(self):
            raise AssertionError("API errors should be returned before reading sentences")

    class FakeRecognition:
        def __init__(self, **kwargs):
            pass

        def call(self, **kwargs):
            return FakeResult()

    monkeypatch.setattr(asr, "Recognition", FakeRecognition)

    exit_code, stdout, stderr = _run_worker_main(monkeypatch, _worker_payload())
    data = json.loads(stdout)

    assert exit_code == 0
    assert data["status"] == "err"
    assert "status: 400" in data["data"]
    assert "code: InvalidModel" in data["data"]
    assert "invalid audio" in data["data"]
    assert "request_id: request-1" in data["data"]
    assert stderr == ""
