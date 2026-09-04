"""Tests for customizable Cohere text embedding model schemas."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from dify_plugin.entities.model import AIModelEntity, FetchFrom, I18nObject, ModelPropertyKey, ModelType

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models.text_embedding.text_embedding import CohereTextEmbeddingModel  # noqa: E402


def _embedding_schema(model: str, *, context_size: int) -> AIModelEntity:
    return AIModelEntity(
        model=model,
        label=I18nObject(en_us=model),
        model_type=ModelType.TEXT_EMBEDDING,
        fetch_from=FetchFrom.PREDEFINED_MODEL,
        model_properties={"context_size": context_size, "max_chunks": 48},
        parameter_rules=[],
    )


@pytest.fixture
def embedding_model() -> CohereTextEmbeddingModel:
    model = CohereTextEmbeddingModel(model_schemas=MagicMock())
    model.predefined_models = MagicMock(
        return_value=[
            _embedding_schema("embed-v4.0", context_size=128000),
            _embedding_schema("embed-multilingual-v3.0", context_size=1024),
        ]
    )
    return model


def test_get_customizable_model_schema_uses_v4_base_for_embed_v4_names(
    embedding_model: CohereTextEmbeddingModel,
) -> None:
    schema = embedding_model.get_customizable_model_schema("embed-v4.0", {})

    assert schema.model == "embed-v4.0"
    assert schema.fetch_from == FetchFrom.CUSTOMIZABLE_MODEL
    assert schema.model_properties[ModelPropertyKey.CONTEXT_SIZE] == 128000


def test_get_customizable_model_schema_uses_multilingual_v3_base_for_other_names(
    embedding_model: CohereTextEmbeddingModel,
) -> None:
    schema = embedding_model.get_customizable_model_schema("my-fine-tuned-embed", {})

    assert schema.model == "my-fine-tuned-embed"
    assert schema.fetch_from == FetchFrom.CUSTOMIZABLE_MODEL
    assert schema.model_properties[ModelPropertyKey.CONTEXT_SIZE] == 1024
