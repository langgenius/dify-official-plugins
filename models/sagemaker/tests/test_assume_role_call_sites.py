"""text_embedding and rerank must request an auditable STS RoleSessionName prefix.

``get_sagemaker_client`` is shared by every model type and does not know which
one is calling, so the embedding and rerank models pass
``role_session_prefix`` explicitly. These tests patch the helper itself, so no
boto3 session and no AWS call is ever made.
"""

import io
import json
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from dify_plugin.entities.model.text_embedding import EmbeddingUsage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.rerank import rerank as rerank_module  # noqa: E402
from models.text_embedding import text_embedding as embedding_module  # noqa: E402

CREDENTIALS = {
    "aws_access_key_id": "test-access-key-id",
    "aws_secret_access_key": "test-secret",
    "aws_region": "us-east-1",
    "sagemaker_endpoint": "test-endpoint",
    "assume_role_arn": "arn:aws:iam::123456789012:role/TestRole",
}


def _runtime_client(payload: dict) -> MagicMock:
    client = MagicMock()
    client.invoke_endpoint.return_value = {
        "Body": io.BytesIO(json.dumps(payload).encode("utf8"))
    }
    return client


def test_text_embedding_passes_embedding_prefix() -> None:
    client = _runtime_client({"embeddings": [[0.1, 0.2, 0.3]]})
    model = embedding_module.SageMakerEmbeddingModel([])
    model._calc_response_usage = MagicMock(
        return_value=EmbeddingUsage(
            tokens=0,
            total_tokens=0,
            unit_price=Decimal("0"),
            price_unit=Decimal("0"),
            total_price=Decimal("0"),
            currency="USD",
            latency=0.0,
        )
    )

    with patch.object(
        embedding_module, "get_sagemaker_client", return_value=client
    ) as factory:
        result = model._invoke("bge-m3", dict(CREDENTIALS), ["hello"])

    factory.assert_called_once_with(
        "sagemaker-runtime",
        CREDENTIALS,
        role_session_prefix="dify-sagemaker-embedding",
    )
    client.invoke_endpoint.assert_called_once()
    assert client.invoke_endpoint.call_args.kwargs["EndpointName"] == "test-endpoint"
    assert result.embeddings == [[0.1, 0.2, 0.3]]


def test_rerank_passes_rerank_prefix() -> None:
    client = _runtime_client({"scores": [0.9, 0.1]})
    model = rerank_module.SageMakerRerankModel([])

    with patch.object(
        rerank_module, "get_sagemaker_client", return_value=client
    ) as factory:
        result = model._invoke(
            "bge-reranker", dict(CREDENTIALS), query="q", docs=["a", "b"]
        )

    factory.assert_called_once_with(
        "sagemaker-runtime",
        CREDENTIALS,
        role_session_prefix="dify-sagemaker-rerank",
    )
    client.invoke_endpoint.assert_called_once()
    assert client.invoke_endpoint.call_args.kwargs["EndpointName"] == "test-endpoint"
    assert [doc.score for doc in result.docs] == [0.9, 0.1]
