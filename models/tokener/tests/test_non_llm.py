import json
from unittest.mock import patch

import pytest
import requests
from dify_plugin.config.config import DifyPluginEnv
from dify_plugin.core.plugin_registration import PluginRegistration
from dify_plugin.entities.model import AIModelEntity, EmbeddingInputType, ModelType
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

from models.rerank.rerank import TokenerRerankModel
from models.text_embedding.text_embedding import TokenerTextEmbeddingModel


def response(body, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body).encode()
    result._content_consumed = True
    return result


def embedding_model():
    schema = AIModelEntity.model_validate(
        {
            "model": "embedding-test",
            "label": {"en_US": "Embedding test"},
            "model_type": "text-embedding",
            "model_properties": {"max_chunks": 2, "context_size": 1},
            "pricing": {"input": "1", "unit": "0.000001", "currency": "USD"},
        }
    )
    return TokenerTextEmbeddingModel(model_schemas=[schema])


def test_dify_registry_reaches_non_llm_public_invokes():
    registration = PluginRegistration(DifyPluginEnv())
    rerank = registration.get_model_instance("tokener", ModelType.RERANK)
    embedding = registration.get_model_instance("tokener", ModelType.TEXT_EMBEDDING)
    embedding.model_schemas = embedding_model().model_schemas
    with patch(
        "requests.post",
        return_value=response(
            {
                "results": [
                    {"index": 0, "relevance_score": 0.9},
                ]
            }
        ),
    ) as post:
        result = rerank.invoke("qwen3-rerank", {"api_key": "test"}, "q", ["a"])
    assert result.docs[0].text == "a"
    assert post.call_args.args[0].endswith("/v1/rerank")
    with patch(
        "requests.post",
        return_value=response(
            {
                "data": [
                    {"index": 0, "embedding": [0.1, 0.2]},
                ],
                "usage": {"total_tokens": 1},
            }
        ),
    ) as post:
        result = embedding.invoke("embedding-test", {"api_key": "test"}, ["a"])
    assert result.embeddings == [[0.1, 0.2]]
    assert post.call_args.kwargs["json"]["model"] == "embedding-test"


def test_public_rerank_preserves_documents_indices_and_threshold():
    model = TokenerRerankModel(model_schemas=[])
    documents = ["same", "", "same"]
    with patch(
        "requests.post",
        return_value=response(
            {
                "results": [
                    {"index": 2, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.0},
                    {"index": 1, "relevance_score": -0.1},
                ]
            }
        ),
    ) as post:
        result = model.invoke(
            "qwen3-rerank",
            {"api_key": "test"},
            "same",
            documents,
            score_threshold=0.0,
            top_n=2,
            user="user",
        )
    assert post.call_args.args == ("https://api.tokener.ai/v1/rerank",)
    assert post.call_args.kwargs["json"] == {
        "model": "qwen3-rerank",
        "query": "same",
        "documents": documents,
        "return_documents": False,
        "top_n": 2,
    }
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer test"
    assert [(d.index, d.text, d.score) for d in result.docs] == [
        (2, "same", 0.9),
        (0, "same", 0.0),
    ]


def test_public_rerank_empty_and_omitted_limit():
    model = TokenerRerankModel(model_schemas=[])
    with patch("requests.post", return_value=response({"results": []})) as post:
        assert model.invoke("qwen3-rerank", {"api_key": "test"}, "q", []).docs == []
        post.assert_not_called()
        assert model.invoke("qwen3-rerank", {"api_key": "test"}, "q", ["a"]).docs == []
    assert "top_n" not in post.call_args.kwargs["json"]


@pytest.mark.parametrize(
    "results",
    [
        [{"index": -1, "relevance_score": 0.9}],
        [{"index": 1, "relevance_score": 0.9}],
        [{"index": True, "relevance_score": 0.9}],
        [{"index": 0, "relevance_score": float("nan")}],
        [{"index": 0, "relevance_score": 0.9}] * 2,
    ],
)
def test_public_rerank_rejects_corrupt_results(results):
    with (
        patch("requests.post", return_value=response({"results": results})),
        pytest.raises(InvokeServerUnavailableError),
    ):
        TokenerRerankModel(model_schemas=[]).invoke("qwen3-rerank", {"api_key": "test"}, "q", ["a"])


@pytest.mark.parametrize("input_type", [EmbeddingInputType.DOCUMENT, EmbeddingInputType.QUERY])
def test_public_embedding_preserves_model_texts_dimensions_and_order(input_type):
    model = embedding_model()
    texts = ["untruncated text " * 100, "second", "third"]
    credentials = {
        "api_key": "test",
        "endpoint_url": "https://wrong.invalid",
        "endpoint_model_name": "different-model",
        "dimensions": 1,
    }
    responses = [
        response(
            {
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ],
                "usage": {"total_tokens": 5},
            }
        ),
        response(
            {
                "data": [
                    {"index": 0, "embedding": [0.5, 0.6]},
                ],
                "usage": {"total_tokens": 2},
            }
        ),
    ]
    with patch("requests.post", side_effect=responses) as post:
        result = model.invoke(
            "embedding-test", credentials, texts, user="user", input_type=input_type
        )
    assert result.embeddings == [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
    assert result.usage.total_tokens == 7
    assert str(result.usage.total_price) == "0.0000070"
    assert result.model == "embedding-test"
    assert post.call_count == 2
    for index, call in enumerate(post.call_args_list):
        assert call.args == ("https://api.tokener.ai/v1/embeddings",)
        assert call.kwargs["json"] == {
            "model": "embedding-test",
            "input": texts[index * 2 : index * 2 + 2],
            "encoding_format": "float",
            "user": "user",
        }
    assert credentials["dimensions"] == 1


@pytest.mark.parametrize(
    "data",
    [
        [{"index": 0, "embedding": [1.0]}],
        [{"index": 0, "embedding": [1.0]}, {"index": 0, "embedding": [2.0]}],
        [{"index": 0, "embedding": [1.0]}, {"index": 2, "embedding": [2.0]}],
        [{"index": 0, "embedding": [1.0]}, {"index": 1, "embedding": [2.0, 3.0]}],
        [{"index": 0, "embedding": [float("inf")]}, {"index": 1, "embedding": [2.0]}],
    ],
)
def test_public_embedding_rejects_corrupt_response(data):
    with (
        patch(
            "requests.post", return_value=response({"data": data, "usage": {"total_tokens": 2}})
        ) as post,
        pytest.raises(InvokeServerUnavailableError),
    ):
        embedding_model().invoke("embedding-test", {"api_key": "test"}, ["a", "b"])
    assert post.call_count == 1


@pytest.mark.parametrize(
    "status,error",
    [
        (400, InvokeBadRequestError),
        (401, InvokeAuthorizationError),
        (403, InvokeAuthorizationError),
        (429, InvokeRateLimitError),
        (503, InvokeServerUnavailableError),
    ],
)
@pytest.mark.parametrize("kind", ["rerank", "embedding"])
def test_public_non_llm_maps_http_errors_without_leaking_response(status, error, kind):
    with (
        patch(
            "requests.post", return_value=response({"error": "sensitive upstream detail"}, status)
        ),
        pytest.raises(error) as caught,
    ):
        if kind == "rerank":
            TokenerRerankModel(model_schemas=[]).invoke(
                "qwen3-rerank", {"api_key": "test"}, "q", ["a"]
            )
        else:
            embedding_model().invoke("embedding-test", {"api_key": "test"}, ["a"])
    assert "sensitive upstream detail" not in str(caught.value)


def test_public_non_llm_does_not_retry_network_failure():
    with (
        patch("requests.post", side_effect=requests.Timeout("private detail")) as post,
        pytest.raises(InvokeConnectionError),
    ):
        embedding_model().invoke("embedding-test", {"api_key": "test"}, ["a"])
    assert post.call_count == 1


def test_rerank_validation_does_not_require_public_directory_membership():
    registration = PluginRegistration(DifyPluginEnv())
    model = registration.get_model_instance("tokener", ModelType.RERANK)
    with (
        patch("requests.get", return_value=response({"data": []})) as get,
        patch("requests.post", return_value=response({"results": []})) as post,
    ):
        model.validate_credentials("qwen3-rerank", {"api_key": "test"})
    get.assert_not_called()
    assert post.call_args.kwargs["json"] == {
        "model": "qwen3-rerank",
        "query": "ping",
        "documents": ["ping"],
        "return_documents": False,
        "top_n": 1,
    }


def test_hidden_rerank_validation_rejects_denied_model_access():
    model = TokenerRerankModel(model_schemas=[])
    with (
        patch("requests.get", return_value=response({"data": []})),
        patch("requests.post", return_value=response({"error": "private detail"}, 403)) as post,
        pytest.raises(CredentialsValidateFailedError) as caught,
    ):
        model.validate_credentials("qwen3-rerank", {"api_key": "test"})
    assert "private detail" not in str(caught.value)
    assert post.call_count == 1
