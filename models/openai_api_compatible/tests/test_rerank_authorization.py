"""Regression tests for rerank request construction.

The official OpenAI-API-compatible plugin rerank implementation used to
emit an empty `Authorization: ` header when the API key was missing,
which unauthenticated gateways reject. The fix attaches `Authorization`
only when an API key is truthy.

These tests drive the model directly so we can capture the headers that
the implementation actually sends and the URL it targets, without needing
a real rerank gateway.
"""

import traceback
from unittest.mock import MagicMock, patch

import pytest
import requests
from dify_plugin.errors.model import InvokeServerUnavailableError

from models.rerank.rerank import OpenAIRerankModel


def _captured_request(mock_post):
    """Extract the kwargs passed to requests.post from the mock call."""
    assert mock_post.call_count == 1
    args, kwargs = mock_post.call_args
    assert len(args) == 0 or isinstance(args[0], str)
    return {
        "url": args[0] if args and isinstance(args[0], str) else kwargs.get("url"),
        "headers": kwargs.get("headers") or (args[1] if len(args) > 1 else {}),
        "json": kwargs.get("json") or (args[2] if len(args) > 2 else {}),
        "timeout": kwargs.get("timeout"),
    }


def _credentials(**overrides):
    creds = {
        "endpoint_url": "https://rerank.example.com/v1",
        "api_key": "",
        "endpoint_model_name": "bge-reranker-v2-m3",
    }
    creds.update(overrides)
    return creds


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"rerank_endpoint_url": ""},
        {"rerank_endpoint_url": " \t "},
    ],
    ids=["missing", "empty", "whitespace"],
)
def test_text_rerank_uses_legacy_endpoint_when_custom_endpoint_is_empty(overrides):
    model = OpenAIRerankModel(model_schemas=[])
    with patch("models.rerank.rerank.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"results": []},
        )
        model._invoke(
            model="bge-reranker-v2-m3",
            credentials=_credentials(**overrides),
            query="q",
            docs=["d1"],
        )

    req = _captured_request(mock_post)
    assert req["url"] == "https://rerank.example.com/v1/rerank"


def test_text_rerank_uses_custom_endpoint_url_exactly_after_trimming():
    model = OpenAIRerankModel(model_schemas=[])
    with patch("models.rerank.rerank.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"results": []},
        )
        model._invoke(
            model="bge-reranker-v2-m3",
            credentials=_credentials(
                rerank_endpoint_url=(
                    "  https://gateway.example.com/v1/reranks/?route=qwen  "
                )
            ),
            query="q",
            docs=["d1"],
        )

    req = _captured_request(mock_post)
    assert req["url"] == "https://gateway.example.com/v1/reranks/?route=qwen"


def test_credential_validation_uses_custom_endpoint_url():
    model = OpenAIRerankModel(model_schemas=[])
    with patch("models.rerank.rerank.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"results": []},
        )
        model.validate_credentials(
            model="bge-reranker-v2-m3",
            credentials=_credentials(
                rerank_endpoint_url="https://gateway.example.com/v1/reranks"
            ),
        )

    req = _captured_request(mock_post)
    assert req["url"] == "https://gateway.example.com/v1/reranks"


def test_request_error_does_not_expose_custom_endpoint_url():
    endpoint_url = "https://user:password@gateway.example.com/v1/reranks?token=secret"
    model = OpenAIRerankModel(model_schemas=[])
    with patch(
        "models.rerank.rerank.requests.post",
        side_effect=requests.exceptions.ConnectionError(endpoint_url),
    ):
        with pytest.raises(InvokeServerUnavailableError) as exc_info:
            model._invoke(
                model="bge-reranker-v2-m3",
                credentials=_credentials(rerank_endpoint_url=endpoint_url),
                query="q",
                docs=["d1"],
            )

    assert str(exc_info.value) == "Rerank API request failed"
    assert endpoint_url not in "".join(traceback.format_exception(exc_info.value))


def test_text_rerank_omits_authorization_when_api_key_missing():
    model = OpenAIRerankModel(model_schemas=[])
    with patch("models.rerank.rerank.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"results": []},
        )
        model._invoke(
            model="bge-reranker-v2-m3",
            credentials=_credentials(api_key=""),
            query="q",
            docs=["d1"],
        )
    req = _captured_request(mock_post)
    assert "Authorization" not in req["headers"], (
        f"Empty Authorization header leaks to the gateway; "
        f"headers={req['headers']!r}"
    )
    assert req["headers"]["Content-Type"] == "application/json"


def test_text_rerank_omits_authorization_when_api_key_none():
    model = OpenAIRerankModel(model_schemas=[])
    with patch("models.rerank.rerank.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"results": []},
        )
        model._invoke(
            model="bge-reranker-v2-m3",
            credentials=_credentials(api_key=None),  # type: ignore[arg-type]
            query="q",
            docs=["d1"],
        )
    req = _captured_request(mock_post)
    assert "Authorization" not in req["headers"]


def test_text_rerank_includes_bearer_when_api_key_present():
    model = OpenAIRerankModel(model_schemas=[])
    with patch("models.rerank.rerank.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"results": []},
        )
        model._invoke(
            model="bge-reranker-v2-m3",
            credentials=_credentials(api_key="sk-test-1234"),
            query="q",
            docs=["d1"],
        )
    req = _captured_request(mock_post)
    assert req["headers"]["Authorization"] == "Bearer sk-test-1234"


def test_multimodal_rerank_omits_authorization_when_api_key_missing():
    from dify_plugin.entities.model.text_embedding import (
        MultiModalContent,
        MultiModalContentType,
    )

    model = OpenAIRerankModel(model_schemas=[])
    query = MultiModalContent(
        content_type=MultiModalContentType.TEXT, content="q"
    )
    docs = [MultiModalContent(content_type=MultiModalContentType.TEXT, content="d1")]
    with patch("models.rerank.rerank.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"results": []},
        )
        model._invoke_multimodal(
            model="qwen3-vl-reranker",
            credentials=_credentials(api_key=""),
            query=query,
            docs=docs,
        )
    req = _captured_request(mock_post)
    assert "Authorization" not in req["headers"], (
        f"Empty Authorization header leaks to the gateway; "
        f"headers={req['headers']!r}"
    )


def test_multimodal_rerank_includes_bearer_when_api_key_present():
    from dify_plugin.entities.model.text_embedding import (
        MultiModalContent,
        MultiModalContentType,
    )

    model = OpenAIRerankModel(model_schemas=[])
    query = MultiModalContent(
        content_type=MultiModalContentType.TEXT, content="q"
    )
    docs = [MultiModalContent(content_type=MultiModalContentType.TEXT, content="d1")]
    with patch("models.rerank.rerank.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"results": []},
        )
        model._invoke_multimodal(
            model="qwen3-vl-reranker",
            credentials=_credentials(api_key="sk-test-5678"),
            query=query,
            docs=docs,
        )
    req = _captured_request(mock_post)
    assert req["headers"]["Authorization"] == "Bearer sk-test-5678"


def test_multimodal_rerank_uses_custom_endpoint_url():
    from dify_plugin.entities.model.text_embedding import (
        MultiModalContent,
        MultiModalContentType,
    )

    model = OpenAIRerankModel(model_schemas=[])
    query = MultiModalContent(
        content_type=MultiModalContentType.TEXT, content="q"
    )
    docs = [MultiModalContent(content_type=MultiModalContentType.TEXT, content="d1")]
    with patch("models.rerank.rerank.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"results": []},
        )
        model._invoke_multimodal(
            model="qwen3-vl-reranker",
            credentials=_credentials(
                rerank_endpoint_url="https://gateway.example.com/v1/reranks"
            ),
            query=query,
            docs=docs,
        )

    req = _captured_request(mock_post)
    assert req["url"] == "https://gateway.example.com/v1/reranks"
