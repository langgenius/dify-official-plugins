import json
import os
import sys
from io import BytesIO, StringIO
from unittest.mock import MagicMock, patch

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


def test_get_audio_type_uses_magic_bytes_before_misleading_filename() -> None:
    file_obj = _named_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x21" + b"\x00" * 16, "upload.wav")

    with patch(
        "models.speech2text.speech2text.AudioSegment.from_file",
        side_effect=AssertionError("magic-byte detection should not decode audio"),
    ):
        assert _model().get_audio_type(file_obj) == "mp3"


def test_invoke_reuses_detected_audio_format_for_decoding() -> None:
    file_obj = _named_bytes(b"RIFF\x24\x00\x00\x00WAVE" + b"\x00" * 16, "upload.mp3")
    audio = MagicMock(frame_rate=16000)
    result = MagicMock()
    result.get_sentence.return_value = [{"text": "hello"}]
    recognition = MagicMock()
    recognition.call.return_value = result

    with patch("models.speech2text.speech2text.AudioSegment.from_file", return_value=audio) as decode_mock:
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
    result.get_sentence.return_value = ["hello", {"text": "world"}]
    recognition = MagicMock()
    recognition.call.return_value = result

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


def test_invoke_uses_subprocess_when_env_set() -> None:
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


def test_invoke_does_not_use_subprocess_when_env_is_zero() -> None:
    audio = MagicMock(frame_rate=16000)
    result = MagicMock()
    result.get_sentence.return_value = [{"text": "hello"}]
    recognition = MagicMock()
    recognition.call.return_value = result

    with patch.dict(os.environ, {"TONGYI_STT_SUBPROCESS": "0"}):
        with patch("models.speech2text.speech2text.AudioSegment.from_file", return_value=audio):
            with patch("models.speech2text.speech2text.Recognition", return_value=recognition):
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
    run_mock.assert_not_called()


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
    import dashscope.audio.asr as asr

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
    import dashscope.audio.asr as asr

    class FakeResult:
        status_code = 400
        message = "invalid audio"

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
    assert "DashScope error: invalid audio (400)" == data["data"]
    assert stderr == ""
