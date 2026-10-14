"""Tests for Qwen3-VL embedding and rerank model exposure (issue #3828)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
from dify_plugin.entities.model.text_embedding import MultiModalContent, MultiModalContentType

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from models.rerank import rerank as rerank_module  # noqa: E402
from models.text_embedding import text_embedding as te  # noqa: E402

GTERerankModel = rerank_module.GTERerankModel
TongyiTextEmbeddingModel = te.TongyiTextEmbeddingModel

CREDENTIALS = {"dashscope_api_key": "test-key"}
BASE_ADDRESS = "https://dashscope.aliyuncs.com/api/v1"
PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class _Qwen3VLEmbeddingResponse:
    def __init__(self) -> None:
        self.status_code = 200
        self.output = {"embeddings": [{"embedding": [0.1, 0.2], "type": "vl"}]}
        self.usage = {"input_tokens": 3, "image_tokens": 0, "total_tokens": 3}


class _Qwen3VLRerankResponse:
    def __init__(self) -> None:
        self.output = MagicMock()
        self.output.results = [
            MagicMock(index=0, relevance_score=0.91, document={"text": "doc-a"}),
            MagicMock(index=1, relevance_score=0.42, document={"image": "data:image/png;base64,abc"}),
        ]


def test_qwen3_vl_embedding_is_vision_model():
    assert TongyiTextEmbeddingModel._is_vision_model("qwen3-vl-embedding") is True


def test_qwen3_vl_rerank_is_vision_model():
    assert GTERerankModel._is_vision_model("qwen3-vl-rerank") is True


def test_qwen3_vl_embedding_usage_counts_total_tokens(monkeypatch):
    monkeypatch.setattr(
        te.dashscope.MultiModalEmbedding,
        "call",
        lambda **kwargs: _Qwen3VLEmbeddingResponse(),
    )

    embeddings, used_tokens = TongyiTextEmbeddingModel.embed_multimodal_documents(
        credentials_kwargs={"dashscope_api_key": "test-key"},
        model="qwen3-vl-embedding",
        documents=[MultiModalContent(content_type=MultiModalContentType.TEXT, content="hello")],
        base_address=BASE_ADDRESS,
        session=requests.Session(),
    )

    assert embeddings == [[0.1, 0.2]]
    assert used_tokens == 3


def test_qwen3_vl_rerank_multimodal_invoke(monkeypatch):
    captured: dict = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        return _Qwen3VLRerankResponse()

    monkeypatch.setattr(rerank_module.dashscope.TextReRank, "call", fake_call)

    model = GTERerankModel(model_schemas=MagicMock())
    result = model._invoke_multimodal(
        model="qwen3-vl-rerank",
        credentials=CREDENTIALS,
        query=MultiModalContent(content_type=MultiModalContentType.IMAGE, content=PNG_BASE64),
        docs=[
            MultiModalContent(content_type=MultiModalContentType.TEXT, content="doc-a"),
            MultiModalContent(content_type=MultiModalContentType.IMAGE, content=PNG_BASE64),
        ],
        top_n=2,
    )

    assert captured["model"] == "qwen3-vl-rerank"
    assert captured["query"]["image"].startswith("data:image/png;base64,")
    assert captured["documents"][0] == {"text": "doc-a"}
    assert captured["documents"][1]["image"].startswith("data:image/png;base64,")
    assert len(result.docs) == 2
    assert result.docs[0].index == 0
    assert result.docs[0].score == pytest.approx(0.91)
    assert result.docs[0].text == "doc-a"


def test_qwen3_vl_rerank_multimodal_not_implemented_for_text_models():
    model = GTERerankModel(model_schemas=MagicMock())
    with pytest.raises(NotImplementedError):
        model._invoke_multimodal(
            model="qwen3-rerank",
            credentials=CREDENTIALS,
            query=MultiModalContent(content_type=MultiModalContentType.TEXT, content="query"),
            docs=[MultiModalContent(content_type=MultiModalContentType.TEXT, content="doc")],
        )
