from unittest.mock import MagicMock, patch

from models.text_embedding.text_embedding import OpenAITextEmbeddingModel


def _successful_embedding_response() -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "data": [{"embedding": [0.1, 0.2, 0.3]}],
        "usage": {"total_tokens": 3},
    }
    return response


def _credentials(**overrides):
    credentials = {
        "endpoint_url": "https://litellm.example.com/v1",
        "endpoint_model_name": "Qwen3-Embedding-8B",
        "api_key": "test-key",
        "context_size": "4096",
        "max_chunks": "8",
    }
    credentials.update(overrides)
    return credentials


@patch("models.text_embedding.text_embedding.requests.post")
def test_text_embedding_sends_configured_encoding_format(mock_post):
    mock_post.return_value = _successful_embedding_response()
    model = OpenAITextEmbeddingModel(model_schemas=[])

    result = model._invoke(
        model="display-name", credentials=_credentials(encoding_format="float"), texts=["ping"]
    )

    payload = mock_post.call_args.kwargs["json"]
    assert payload == {"model": "Qwen3-Embedding-8B", "input": ["ping"], "encoding_format": "float"}
    assert result.embeddings == [[0.1, 0.2, 0.3]]


@patch("models.text_embedding.text_embedding.requests.post")
def test_text_embedding_omits_unset_encoding_format(mock_post):
    mock_post.return_value = _successful_embedding_response()
    model = OpenAITextEmbeddingModel(model_schemas=[])

    model._invoke(
        model="display-name", credentials=_credentials(encoding_format="not_set"), texts=["ping"]
    )

    payload = mock_post.call_args.kwargs["json"]
    assert payload == {"model": "Qwen3-Embedding-8B", "input": ["ping"]}


@patch("models.text_embedding.text_embedding.requests.post")
def test_text_embedding_validate_credentials_uses_runtime_payload_shape(mock_post):
    mock_post.return_value = _successful_embedding_response()
    model = OpenAITextEmbeddingModel(model_schemas=[])

    model.validate_credentials(
        model="display-name", credentials=_credentials(encoding_format="float")
    )

    payload = mock_post.call_args.kwargs["json"]
    assert payload == {"model": "Qwen3-Embedding-8B", "input": ["ping"], "encoding_format": "float"}
