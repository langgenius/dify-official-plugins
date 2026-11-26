import io
import os
import struct
import sys
import wave
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
)

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


def test_merge_wav_segments_rejects_truncated_header() -> None:
    with pytest.raises(InvokeBadRequestError, match="invalid WAVE segment"):
        merge_wav_segments([b"RIFF"])


def test_merge_wav_segments_rejects_truncated_frame_data() -> None:
    truncated_segment = (
        b"RIFF"
        + struct.pack("<I", 40)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, 8_000, 16_000, 2, 16)
        + b"data"
        + struct.pack("<I", 4)
        + b"\x00\x00"
    )

    with pytest.raises(InvokeBadRequestError, match="truncated WAVE segment 1"):
        merge_wav_segments([truncated_segment])


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
            return_value=[
                SimpleNamespace(status_code=200, output=SimpleNamespace(audio={"data": "pcm"}))
            ],
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


def _placeholder_wav(
    frames: bytes, *, sample_rate: int = 24_000, declared_size: int = 0x7FFFFFEB
) -> bytes:
    """Build a WAVE whose data chunk declares DashScope's streaming placeholder size."""
    block_align = 2
    return (
        b"RIFF"
        + struct.pack("<I", declared_size + 36)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * block_align, block_align, 16)
        + b"data"
        + struct.pack("<I", declared_size)
        + frames
    )


def test_merge_wav_segments_accepts_streaming_placeholder_sizes() -> None:
    frames = b"\x01\x00\x02\x00\x03\x00"

    merged = merge_wav_segments([_placeholder_wav(frames)])

    assert merged.startswith(b"RIFF")
    assert _wav_frames(merged) == (24_000, frames)


def test_merge_wav_segments_drops_unaligned_placeholder_tail() -> None:
    frames = b"\x01\x00\x02\x00\x03"  # a trailing byte cannot form a frame

    merged = merge_wav_segments([_placeholder_wav(frames)])

    assert _wav_frames(merged) == (24_000, frames[:-1])


def _http_response(
    status_code: int, payload: dict | None = None, content: bytes = b""
) -> MagicMock:
    response = MagicMock(status_code=status_code, content=content, text=str(payload))
    response.json.return_value = payload or {}
    return response


def test_qwen_audio_tts_uses_speech_synthesizer_http_api() -> None:
    model = TongyiText2SpeechModel(model_schemas=MagicMock())
    audio = _placeholder_wav(b"\x01\x00\x02\x00")

    with (
        patch.object(model, "_get_model_word_limit", return_value=512),
        patch("models.tts.tts.get_http_base_address", return_value="https://host/api/v1"),
        patch("models.tts.tts.MultiModalConversation.call") as multimodal_call,
        patch(
            "models.tts.tts.requests.post",
            return_value=_http_response(200, {"output": {"audio": {"url": "https://audio"}}}),
        ) as post,
        patch("models.tts.tts.requests.get", return_value=_http_response(200, content=audio)),
    ):
        output = list(
            model._tts_invoke_streaming(
                model="qwen-audio-3.1-tts-plus",
                credentials={"dashscope_api_key": "test-key"},
                content_text="hello",
                voice="longanhuan_v3.1",
            )
        )

    multimodal_call.assert_not_called()
    assert post.call_args.args[0] == "https://host/api/v1/services/audio/tts/SpeechSynthesizer"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert post.call_args.kwargs["json"] == {
        "model": "qwen-audio-3.1-tts-plus",
        "input": {"text": "hello", "voice": "longanhuan_v3.1", "format": "wav"},
    }
    assert _wav_frames(output[0]) == (24_000, b"\x01\x00\x02\x00")


def test_qwen_audio_tts_surfaces_dashscope_error() -> None:
    model = TongyiText2SpeechModel(model_schemas=MagicMock())
    error = {"code": "InvalidParameter", "message": "voice not found", "request_id": "rid"}

    with (
        patch.object(model, "_get_model_word_limit", return_value=512),
        patch("models.tts.tts.get_http_base_address", return_value="https://host/api/v1"),
        patch("models.tts.tts.requests.post", return_value=_http_response(400, error)),
        pytest.raises(InvokeBadRequestError, match="voice not found.*InvalidParameter.*rid"),
    ):
        list(
            model._tts_invoke_streaming(
                model="qwen-audio-3.1-tts-flash",
                credentials={"dashscope_api_key": "test-key"},
                content_text="hello",
                voice="Cherry",
            )
        )


def test_validate_credentials_performs_a_real_synthesis() -> None:
    model = TongyiText2SpeechModel(model_schemas=MagicMock())
    calls: list[str] = []

    def synthesize(**kwargs):
        calls.append(kwargs["voice"])
        raise InvokeBadRequestError("invalid api key")
        yield b""  # pragma: no cover

    with (
        patch.object(model, "_get_model_default_voice", return_value="longanhuan_v3.1"),
        patch.object(model, "_tts_invoke_streaming", side_effect=synthesize),
        pytest.raises(CredentialsValidateFailedError, match="invalid api key"),
    ):
        model.validate_credentials("qwen-audio-3.1-tts-plus", {"dashscope_api_key": "bad"})

    assert calls == ["longanhuan_v3.1"]
