"""User-added (Add Model) models must resolve to a schema, otherwise Dify drops
them from the model lists and the default model selectors."""

import io
import os
import sys
import wave
from unittest.mock import patch

import pytest
from dify_plugin.entities.model import FetchFrom, ModelPropertyKey, ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.rerank.rerank import GTERerankModel
from models.speech2text.speech2text import TongyiSpeech2TextModel
from models.text_embedding.text_embedding import TongyiTextEmbeddingModel
from models.tts.tts import TongyiText2SpeechModel


@pytest.mark.parametrize(
    ("model_class", "model_type"),
    [
        (TongyiText2SpeechModel, ModelType.TTS),
        (TongyiSpeech2TextModel, ModelType.SPEECH2TEXT),
        (TongyiTextEmbeddingModel, ModelType.TEXT_EMBEDDING),
        (GTERerankModel, ModelType.RERANK),
    ],
)
def test_custom_model_schema_matches_model_type(model_class, model_type) -> None:
    schema = model_class(model_schemas=[]).get_customizable_model_schema(
        "brand-new-model", {"dashscope_api_key": "k", "context_size": "2048"}
    )

    assert schema is not None
    assert schema.model == "brand-new-model"
    assert schema.model_type == model_type
    assert schema.fetch_from == FetchFrom.CUSTOMIZABLE_MODEL


def test_tts_custom_model_exposes_default_voice() -> None:
    schema = TongyiText2SpeechModel(model_schemas=[]).get_customizable_model_schema("m", {})

    voices = schema.model_properties[ModelPropertyKey.VOICES]
    default_voice = schema.model_properties[ModelPropertyKey.DEFAULT_VOICE]
    assert default_voice in [voice["mode"] for voice in voices]


@pytest.mark.parametrize(
    ("model", "expected_voices"),
    [
        (
            "qwen-audio-3.1-tts-plus",
            ["longanlingxin_v3.1", "xunanchuan_v3.1", "longanhuan_v3.1", "longanfengyue_v3.1"],
        ),
        ("qwen-audio-3.0-tts-plus", ["longanlingxin", "longanlufeng"]),
        (
            "qwen-audio-3.0-tts-flash",
            ["longanfengyue", "longanyuanfei", "longanlingxi", "longanxiaoxin", "longanhuan_v3.6"],
        ),
    ],
)
def test_qwen_audio_tts_custom_model_uses_its_own_voices(
    model: str, expected_voices: list[str]
) -> None:
    schema = TongyiText2SpeechModel(model_schemas=[]).get_customizable_model_schema(model, {})

    voices = [voice["mode"] for voice in schema.model_properties[ModelPropertyKey.VOICES]]
    assert voices == expected_voices
    assert schema.model_properties[ModelPropertyKey.DEFAULT_VOICE] == expected_voices[0]


@pytest.mark.parametrize(
    ("model", "limit"),
    [("qwen-audio-3.1-asr-flash", 7), ("qwen-audio-3.1-asr-flash-filetrans", 100)],
)
def test_speech2text_custom_model_upload_limit(model: str, limit: int) -> None:
    schema = TongyiSpeech2TextModel(model_schemas=[]).get_customizable_model_schema(model, {})

    assert schema.model_properties[ModelPropertyKey.FILE_UPLOAD_LIMIT] == limit


def test_speech2text_validation_probes_with_mono_audio() -> None:
    model = TongyiSpeech2TextModel(model_schemas=[])
    seen = {}

    def fake_invoke(_model, _credentials, file, user=None):
        with wave.open(io.BytesIO(file.read()), "rb") as reader:
            seen["channels"] = reader.getnchannels()
        return ""

    with patch.object(TongyiSpeech2TextModel, "_invoke", side_effect=fake_invoke):
        model.validate_credentials("qwen-audio-3.1-asr-flash", {"dashscope_api_key": "k"})

    assert seen["channels"] == 1


def test_speech2text_validation_accepts_no_words_for_silent_probe() -> None:
    model = TongyiSpeech2TextModel(model_schemas=[])
    no_words = ValueError(
        "DashScope error: ASR_RESPONSE_HAVE_NO_WORDS (status: 400, code: CLIENT_ERROR)"
    )
    with patch.object(TongyiSpeech2TextModel, "_invoke", side_effect=no_words):
        model.validate_credentials("qwen-audio-3.1-asr-flash", {"dashscope_api_key": "k"})

    unauthorized = ValueError("DashScope error: Invalid API-key (status: 401)")
    with (
        patch.object(TongyiSpeech2TextModel, "_invoke", side_effect=unauthorized),
        pytest.raises(CredentialsValidateFailedError, match="401"),
    ):
        model.validate_credentials("qwen-audio-3.1-asr-flash", {"dashscope_api_key": "k"})


def test_embedding_and_rerank_use_configured_context_size() -> None:
    credentials = {"context_size": "2048"}

    embedding = TongyiTextEmbeddingModel(model_schemas=[]).get_customizable_model_schema(
        "m", credentials
    )
    rerank = GTERerankModel(model_schemas=[]).get_customizable_model_schema("m", credentials)

    assert embedding.model_properties[ModelPropertyKey.CONTEXT_SIZE] == 2048
    assert rerank.model_properties[ModelPropertyKey.CONTEXT_SIZE] == 2048
