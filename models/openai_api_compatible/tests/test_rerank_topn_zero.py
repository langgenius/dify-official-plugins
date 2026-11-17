"""top_n=0 must truncate to an empty result in text rerank mode.

The text-mode `_invoke` applied the `top_n` limit with `if top_n:`, which
treated `top_n=0` as falsy and skipped the truncation, returning every
result. The multimodal mode already used `if top_n is not None:` and the
payload builder deliberately handled `top_n=0`, so the two paths disagreed.
"""

from unittest.mock import MagicMock, patch

from models.rerank.rerank import OpenAIRerankModel


def _credentials() -> dict:
    return {
        "endpoint_url": "https://rerank.example.com/v1",
        "api_key": "",
        "endpoint_model_name": "bge-reranker-v2-m3",
    }


def _model() -> OpenAIRerankModel:
    return OpenAIRerankModel(model_schemas=[])


def _results(*pairs):
    return {
        "results": [{"index": idx, "relevance_score": score} for idx, score in pairs],
    }


def test_text_rerank_top_n_zero_returns_no_docs():
    model = _model()
    with patch("models.rerank.rerank.requests.post") as mock_post:
        # A server that ignores top_n=0 and returns every document would
        # otherwise leak all results through.
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: _results((0, 0.9), (1, 0.8), (2, 0.7)),
        )
        result = model._invoke(
            model="bge-reranker-v2-m3",
            credentials=_credentials(),
            query="q",
            docs=["d0", "d1", "d2"],
            top_n=0,
        )

    assert result.docs == []


def test_text_rerank_top_n_one_returns_single_doc():
    model = _model()
    with patch("models.rerank.rerank.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: _results((0, 0.9), (1, 0.8)),
        )
        result = model._invoke(
            model="bge-reranker-v2-m3",
            credentials=_credentials(),
            query="q",
            docs=["d0", "d1"],
            top_n=1,
        )

    assert len(result.docs) == 1
    assert result.docs[0].index == 0


def test_text_rerank_top_n_none_returns_all_docs():
    model = _model()
    with patch("models.rerank.rerank.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: _results((0, 0.9), (1, 0.8)),
        )
        result = model._invoke(
            model="bge-reranker-v2-m3",
            credentials=_credentials(),
            query="q",
            docs=["d0", "d1"],
            top_n=None,
        )

    assert len(result.docs) == 2
