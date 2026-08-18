from math import isfinite
from pathlib import Path

import pytest


pytestmark = pytest.mark.live

_AUDIO_FILE = Path(__file__).resolve().parents[2] / "_assets" / "audio.mp3"


def test_embedding_models_return_vectors_and_usage(
    live_embedding, live_credentials, embedding_model
):
    result = live_embedding.invoke(
        model=embedding_model,
        credentials=live_credentials,
        texts=["A small blue circle.", "一个小蓝色圆形。"],
        user="dify-openai-live-test",
    )

    assert result.model == embedding_model
    assert len(result.embeddings) == 2
    assert len({len(vector) for vector in result.embeddings}) == 1
    assert all(vector for vector in result.embeddings)
    assert all(isfinite(value) for vector in result.embeddings for value in vector)
    assert result.usage.tokens > 0
    assert result.usage.total_tokens == result.usage.tokens
    assert result.usage.latency >= 0


def test_moderation_models_accept_benign_text(
    live_moderation, live_credentials, moderation_model
):
    flagged = live_moderation.invoke(
        model=moderation_model,
        credentials=live_credentials,
        text="A blue circle is beside a green square.",
        user="dify-openai-live-test",
    )

    assert flagged is False


def test_speech_to_text_models_transcribe_demo_audio(
    live_speech2text, live_credentials, speech2text_model
):
    with _AUDIO_FILE.open("rb") as audio:
        transcription = live_speech2text.invoke(
            model=speech2text_model,
            credentials=live_credentials,
            file=audio,
            user="dify-openai-live-test",
        )

    assert transcription.strip()


def test_tts_models_stream_audio(live_tts, live_credentials, tts_model):
    voice = live_tts._get_model_default_voice(tts_model, live_credentials)
    stream = live_tts.invoke(
        model=tts_model,
        tenant_id="dify-openai-live-test",
        credentials=live_credentials,
        content_text="Hi.",
        voice=voice,
        user="dify-openai-live-test",
    )
    chunks = list(stream)

    assert voice
    assert all(isinstance(chunk, bytes) for chunk in chunks)
    assert sum(map(len, chunks)) > 0
