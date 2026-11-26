"""User-added (Add Model) models must resolve to a schema, otherwise Dify drops
them from the model lists and the default model selectors."""

import os
import sys

import pytest
from dify_plugin.entities.model import FetchFrom, ModelPropertyKey, ModelType

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


def test_embedding_and_rerank_use_configured_context_size() -> None:
    credentials = {"context_size": "2048"}

    embedding = TongyiTextEmbeddingModel(model_schemas=[]).get_customizable_model_schema("m", credentials)
    rerank = GTERerankModel(model_schemas=[]).get_customizable_model_schema("m", credentials)

    assert embedding.model_properties[ModelPropertyKey.CONTEXT_SIZE] == 2048
    assert rerank.model_properties[ModelPropertyKey.CONTEXT_SIZE] == 2048
