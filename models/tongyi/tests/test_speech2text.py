import os
import sys
from io import BytesIO
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.speech2text.speech2text import TongyiSpeech2TextModel


def _model() -> TongyiSpeech2TextModel:
    return TongyiSpeech2TextModel(model_schemas=MagicMock())


def _named_bytes(data: bytes, name: str) -> BytesIO:
    file_obj = BytesIO(data)
    file_obj.name = name
    return file_obj


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
