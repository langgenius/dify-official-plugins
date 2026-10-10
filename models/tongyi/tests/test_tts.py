import io
import os
import struct
import sys
import wave
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from dify_plugin.errors.model import InvokeBadRequestError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.tts.tts import TongyiText2SpeechModel, _StreamingWavMerger, merge_wav_segments


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


def test_long_tts_output_is_emitted_incrementally_per_sentence() -> None:
    """Each sentence's audio should reach the consumer as soon as it's ready,
    not only after the whole reply has been synthesized (the timeout this PR
    fixes: see #41456)."""
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

    # Two sentences -> two separate chunks reach the consumer, not one
    # buffered chunk after everything finishes.
    assert len(output) == 2
    # First chunk carries the WAV header (playable on its own as first audio).
    assert output[0].startswith(b"RIFF")
    assert output[1] == b"\x02\x00"
    # Concatenating every chunk in arrival order reproduces a single valid,
    # playable WAV stream with all frames intact.
    full_stream = b"".join(output)
    assert _wav_frames(full_stream) == (16_000, b"\x01\x00\x02\x00")


def test_streaming_wav_merger_first_chunk_is_immediately_playable() -> None:
    """The first sentence's chunk alone (header + its frames) must open as a
    valid WAV even though the header's size fields are placeholders, since a
    consumer may start playback before later sentences arrive."""
    merger = _StreamingWavMerger()
    first_chunk = merger.feed(_wav(b"\x01\x00\x02\x00"), 1)

    with wave.open(io.BytesIO(first_chunk), "rb") as reader:
        assert reader.getframerate() == 16_000
        assert reader.readframes(2) == b"\x01\x00\x02\x00"


def test_streaming_wav_merger_concatenated_chunks_play_back_correctly() -> None:
    """Chunks from multiple feed() calls, concatenated in order, must
    reassemble into one playable WAV with every sentence's frames intact and
    correctly ordered — even though each chunk's own size fields are
    placeholders."""
    merger = _StreamingWavMerger()
    chunks = [
        merger.feed(_wav(b"\x01\x00\x02\x00"), 1),
        merger.feed(_wav(b"\x03\x00\x04\x00"), 2),
        merger.feed(_wav(b"\x05\x00\x06\x00"), 3),
    ]

    assert _wav_frames(b"".join(chunks)) == (
        16_000,
        b"\x01\x00\x02\x00\x03\x00\x04\x00\x05\x00\x06\x00",
    )


def test_streaming_wav_merger_rejects_incompatible_formats() -> None:
    merger = _StreamingWavMerger()
    merger.feed(_wav(b"\x00\x00"), 1)

    with pytest.raises(InvokeBadRequestError, match="incompatible audio formats"):
        merger.feed(_wav(b"\x00\x00", sample_rate=24_000), 2)


def test_streaming_wav_merger_rejects_truncated_segment() -> None:
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
        _StreamingWavMerger().feed(truncated_segment, 1)


def test_streaming_wav_merger_rejects_invalid_segment() -> None:
    with pytest.raises(InvokeBadRequestError, match="invalid WAVE segment"):
        _StreamingWavMerger().feed(b"RIFF", 1)


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
