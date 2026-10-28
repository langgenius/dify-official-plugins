"""Tests for the qwen3-vl-embedding / qwen3-vl-rerank model registrations (#3828).

qwen3-vl-embedding is served only by the DashScope multimodal embedding
endpoint, so plain-text invocations must dispatch to
dashscope.MultiModalEmbedding.call (like multimodal-embedding-v1), not
dashscope.TextEmbedding.call, which would hit the wrong endpoint.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from models.text_embedding.text_embedding import TongyiTextEmbeddingModel

MODEL_DIR = Path(__file__).parents[1] / "models"


def _fake_response():
    return SimpleNamespace(
        status_code=200,
        output={"embeddings": [{"embedding": [0.1, 0.2], "type": "text", "index": 0}]},
        usage={"total_tokens": 5},
    )


def test_qwen3_vl_embedding_yaml_registration():
    schema = yaml.safe_load(
        (MODEL_DIR / "text_embedding" / "qwen3-vl-embedding.yaml").read_text(encoding="utf-8")
    )
    assert schema["model"] == "qwen3-vl-embedding"
    assert schema["model_type"] == "text-embedding"
    assert schema["model_properties"]["context_size"] == 32000
    assert "vision" in schema["features"]


def test_qwen3_vl_rerank_yaml_registration():
    schema = yaml.safe_load(
        (MODEL_DIR / "rerank" / "qwen3-vl-rerank.yaml").read_text(encoding="utf-8")
    )
    assert schema["model"] == "qwen3-vl-rerank"
    assert schema["model_type"] == "rerank"
    position = yaml.safe_load((MODEL_DIR / "rerank" / "_position.yaml").read_text())
    assert "qwen3-vl-rerank" in position


def test_qwen3_vl_embedding_dispatches_to_multimodal_endpoint():
    with patch("models.text_embedding.text_embedding.dashscope") as mock_dashscope:
        mock_dashscope.MultiModalEmbedding.call.return_value = _fake_response()
        embeddings, tokens = TongyiTextEmbeddingModel.embed_documents(
            credentials_kwargs={"dashscope_api_key": "test-key"},
            model="qwen3-vl-embedding",
            texts=["hello"],
            base_address=None,
        )
    assert mock_dashscope.MultiModalEmbedding.call.called
    assert not mock_dashscope.TextEmbedding.call.called
    assert mock_dashscope.MultiModalEmbedding.call.call_args.kwargs["input"] == [
        {"text": "hello"}
    ]
    assert embeddings == [[0.1, 0.2]]
    assert tokens == 5


def test_text_embedding_v4_still_uses_text_endpoint():
    with patch("models.text_embedding.text_embedding.dashscope") as mock_dashscope:
        mock_dashscope.TextEmbedding.call.return_value = _fake_response()
        embeddings, _ = TongyiTextEmbeddingModel.embed_documents(
            credentials_kwargs={"dashscope_api_key": "test-key"},
            model="text-embedding-v4",
            texts=["hello"],
            base_address=None,
        )
    assert mock_dashscope.TextEmbedding.call.called
    assert not mock_dashscope.MultiModalEmbedding.call.called
    assert embeddings == [[0.1, 0.2]]


def _fake_vl_response():
    return SimpleNamespace(
        status_code=200,
        output={"embeddings": [{"embedding": [0.3, 0.4], "type": "vl", "index": 0}]},
        usage={"input_tokens": 12, "image_tokens": 256, "total_tokens": 268},
    )


def test_qwen3_vl_embedding_multimodal_path_and_usage():
    # The KB multimodal path must call the DashScope multimodal endpoint with
    # documented content shapes and count usage for qwen3-vl-embedding's "vl"
    # embedding type (total_tokens = input + image tokens).
    from dify_plugin.entities.model.text_embedding import (
        MultiModalContent,
        MultiModalContentType,
    )

    png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    with patch("models.text_embedding.text_embedding.dashscope") as mock_dashscope:
        mock_dashscope.MultiModalEmbedding.call.return_value = _fake_vl_response()
        embeddings, tokens = TongyiTextEmbeddingModel.embed_multimodal_documents(
            credentials_kwargs={"dashscope_api_key": "test-key"},
            model="qwen3-vl-embedding",
            documents=[
                MultiModalContent(
                    content_type=MultiModalContentType.IMAGE, content=png_b64
                )
            ],
            base_address=None,
        )
    call_input = mock_dashscope.MultiModalEmbedding.call.call_args.kwargs["input"]
    assert call_input == [{"image": f"data:image/png;base64,{png_b64}"}]
    assert embeddings == [[0.3, 0.4]]
    assert tokens == {"total": 268, "text": 12, "image": 256}


def test_qwen3_vl_embedding_split_pricing_is_exact():
    # qwen3-vl-embedding bills image tokens at $0.258/MTok vs text $0.1/MTok
    # (multimodal-embedding-api-reference). The flat pricing schema carries the
    # text rate, so the plugin must price image tokens at 2.58x when DashScope
    # returns the split, instead of billing all tokens at the text rate.
    from decimal import Decimal
    from types import SimpleNamespace as NS
    from unittest.mock import MagicMock

    model = TongyiTextEmbeddingModel(model_schemas=MagicMock())
    model.started_at = 0.0

    def fake_get_price(model, credentials, price_type, tokens):
        return NS(
            unit_price=Decimal("0.1"),
            unit=Decimal("0.000001"),
            total_amount=Decimal("0.1") * Decimal("0.000001") * Decimal(tokens),
            currency="USD",
        )

    model.get_price = fake_get_price
    usage = model._calc_response_usage(
        model="qwen3-vl-embedding",
        credentials={},
        tokens=1290,
        text_tokens=43,
        image_tokens=1247,
    )
    assert usage.tokens == 1290
    expected = Decimal("0.1") * Decimal("0.000001") * (Decimal(43) + Decimal("2.58") * Decimal(1247))
    assert usage.total_price == expected
    # Sanity: flat text-rate billing would have undercounted.
    assert usage.total_price > Decimal("0.1") * Decimal("0.000001") * Decimal(1290)

    # Text-only invocations keep the flat (exact) text rate.
    usage_text = model._calc_response_usage(
        model="qwen3-vl-embedding", credentials={}, tokens=43, text_tokens=43
    )
    assert usage_text.total_price == Decimal("0.1") * Decimal("0.000001") * Decimal(43)

    # Models without a documented split keep flat pricing.
    usage_other = model._calc_response_usage(
        model="multimodal-embedding-v1",
        credentials={},
        tokens=100,
        text_tokens=60,
        image_tokens=40,
    )
    assert usage_other.total_price == Decimal("0.1") * Decimal("0.000001") * Decimal(100)
