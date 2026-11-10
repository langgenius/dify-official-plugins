import json
from unittest.mock import MagicMock, patch

from dify_plugin.entities.model import ModelPropertyKey

from models.text_embedding.text_embedding import LiteLLMTextEmbeddingModel

MODEL = "text-embedding-3-large"


def _credentials(**overrides) -> dict:
    credentials = {
        "endpoint_url": "http://localhost:4000",
        "context_size": "8192",
        "max_chunks": "2",
    }
    credentials.update(overrides)
    return credentials


def _embedding_response(count: int) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "data": [{"embedding": [0.1, 0.2, 0.3]} for _ in range(count)],
        "usage": {"total_tokens": 3},
    }
    return response


def test_schema_uses_max_chunks_from_credentials() -> None:
    model = LiteLLMTextEmbeddingModel(model_schemas=[])

    schema = model.get_customizable_model_schema(MODEL, _credentials(max_chunks="16"))

    assert schema.model_properties[ModelPropertyKey.MAX_CHUNKS] == 16
    assert schema.model_properties[ModelPropertyKey.CONTEXT_SIZE] == 8192


def test_schema_falls_back_to_one_chunk() -> None:
    model = LiteLLMTextEmbeddingModel(model_schemas=[])

    schema = model.get_customizable_model_schema(MODEL, _credentials(max_chunks=""))

    assert schema.model_properties[ModelPropertyKey.MAX_CHUNKS] == 1


@patch("dify_plugin.interfaces.model.openai_compatible.text_embedding.requests.post")
def test_invoke_batches_by_max_chunks(post) -> None:
    post.side_effect = [_embedding_response(2), _embedding_response(1)]
    model = LiteLLMTextEmbeddingModel(model_schemas=[])
    # `_get_max_chunks` reads the schema, so register the customizable schema.
    model.get_model_schema = lambda m, c=None: model.get_customizable_model_schema(
        m, c or _credentials()
    )

    result = model._invoke(MODEL, _credentials(), ["a", "b", "c"])

    assert post.call_count == 2
    assert len(result.embeddings) == 3
    first_call = post.call_args_list[0]
    assert first_call.args[0] == "http://localhost:4000/embeddings"
    assert json.loads(first_call.kwargs["data"])["input"] == ["a", "b"]


@patch("dify_plugin.interfaces.model.openai_compatible.text_embedding.requests.post")
def test_invoke_calls_the_embeddings_route_with_optional_key(post) -> None:
    post.return_value = _embedding_response(1)
    model = LiteLLMTextEmbeddingModel(model_schemas=[])
    model.get_model_schema = lambda m, c=None: model.get_customizable_model_schema(
        m, c or _credentials()
    )

    model._invoke(MODEL, _credentials(max_chunks="1"), ["a"])
    model._invoke(MODEL, _credentials(max_chunks="1", api_key="sk-test"), ["a"])

    without_key, with_key = post.call_args_list
    assert without_key.args[0] == "http://localhost:4000/embeddings"
    assert "Authorization" not in without_key.kwargs["headers"]
    assert with_key.kwargs["headers"]["Authorization"] == "Bearer sk-test"
    assert json.loads(with_key.kwargs["data"])["encoding_format"] == "float"
