import io
import os
import sys
import wave
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from dify_plugin.errors.model import InvokeBadRequestError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.tts.tts import TongyiText2SpeechModel, merge_wav_segments


def _wav(frames: bytes, *, sample_rate: int = 16_000) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(frames)
    return output.getvalue()


def _wav_frames(audio: bytes) -> tuple[int, bytes]:
    with wave.open(io.BytesIO(audio), "rb") as reader:
        return reader.getframerate(), reader.readframes(reader.getnframes())


def test_merge_wav_segments_builds_one_valid_container() -> None:
    first = _wav(b"\x01\x00\x02\x00")
    second = _wav(b"\x03\x00\x04\x00")

    merged = merge_wav_segments([first, second])

    assert merged.startswith(b"RIFF")
    assert merged[8:12] == b"WAVE"
    assert _wav_frames(merged) == (16_000, b"\x01\x00\x02\x00\x03\x00\x04\x00")


def test_merge_wav_segments_rejects_incompatible_formats() -> None:
    with pytest.raises(InvokeBadRequestError, match="incompatible audio formats"):
        merge_wav_segments([_wav(b"\x00\x00"), _wav(b"\x00\x00", sample_rate=24_000)])


def test_long_tts_output_is_merged_before_it_is_emitted() -> None:
    model = TongyiText2SpeechModel(model_schemas=MagicMock())
    first = _wav(b"\x01\x00")
    second = _wav(b"\x02\x00")
    remote_responses = [
        [
            SimpleNamespace(status_code=200, output=SimpleNamespace(audio={"data": "pcm"})),
            SimpleNamespace(status_code=200, output=SimpleNamespace(audio={"url": "first"})),
        ],
        [
            SimpleNamespace(status_code=200, output=SimpleNamespace(audio={"data": "pcm"})),
            SimpleNamespace(status_code=200, output=SimpleNamespace(audio={"url": "second"})),
        ],
    ]

    def urlopen_response(audio: bytes) -> MagicMock:
        response = MagicMock()
        response.read.return_value = audio
        response.__enter__.return_value = response
        return response

    with (
        patch.object(model, "_get_model_word_limit", return_value=3),
        patch("models.tts.tts.get_http_base_address", return_value=None),
        patch("models.tts.tts.MultiModalConversation.call", side_effect=remote_responses),
        patch(
            "models.tts.tts.urlopen",
            side_effect=[urlopen_response(first), urlopen_response(second)],
        ),
    ):
        output = list(
            model._tts_invoke_streaming(
                model="qwen3-tts-flash",
                credentials={"dashscope_api_key": "test-key"},
                content_text="abcdef",
                voice="Cherry",
            )
        )

    assert len(output) == 1
    assert _wav_frames(output[0]) == (16_000, b"\x01\x00\x02\x00")


def test_tts_requires_the_final_audio_url() -> None:
    model = TongyiText2SpeechModel(model_schemas=MagicMock())

    with (
        patch.object(model, "_get_model_word_limit", return_value=512),
        patch("models.tts.tts.get_http_base_address", return_value=None),
        patch(
            "models.tts.tts.MultiModalConversation.call",
            return_value=[SimpleNamespace(status_code=200, output=SimpleNamespace(audio={"data": "pcm"}))],
        ),
        pytest.raises(InvokeBadRequestError, match="No audio URL in response"),
    ):
        list(
            model._tts_invoke_streaming(
                model="qwen3-tts-flash",
                credentials={"dashscope_api_key": "test-key"},
                content_text="hello",
                voice="Cherry",
            )
        )
