import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from dify_plugin.entities.model.text_embedding import (
    EmbeddingUsage,
    MultiModalContent,
    MultiModalContentType,
)

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from models.text_embedding import text_embedding as te  # noqa: E402

TongyiTextEmbeddingModel = te.TongyiTextEmbeddingModel

CREDENTIALS = {"dashscope_api_key": "test-key"}
BASE_ADDRESS = "https://dashscope.aliyuncs.com/api/v1"
TEXT_MODEL = "text-embedding-v3"
MULTIMODAL_MODEL = "multimodal-embedding-v1"


class _TextResponse:
    def __init__(self) -> None:
        self.status_code = 200
        self.output = {"embeddings": [{"embedding": [0.1, 0.2, 0.3], "type": "text"}]}
        self.usage = {"total_tokens": 7}


class _MultiModalResponse:
    def __init__(self) -> None:
        self.status_code = 200
        self.output = {"embeddings": [{"embedding": [0.4, 0.5], "type": "text"}]}
        self.usage = {"input_tokens": 5, "image_tokens": 0}


def _usage() -> EmbeddingUsage:
    return EmbeddingUsage(
        tokens=0,
        total_tokens=0,
        unit_price=Decimal("0"),
        price_unit=Decimal("0"),
        total_price=Decimal("0"),
        currency="RMB",
        latency=0,
    )


def _model(max_chunks: int = 10) -> TongyiTextEmbeddingModel:
    model = TongyiTextEmbeddingModel(model_schemas=MagicMock())
    model._get_context_size = MagicMock(return_value=8192)
    model._get_max_chunks = MagicMock(return_value=max_chunks)
    model._get_num_tokens_by_gpt2 = MagicMock(return_value=1)
    model._calc_response_usage = MagicMock(return_value=_usage())
    return model


def test_text_embedding_call_uses_sdk_managed_session() -> None:
    with patch.object(te.dashscope.TextEmbedding, "call", return_value=_TextResponse()) as call:
        result = TongyiTextEmbeddingModel.embed_documents(
            credentials_kwargs=CREDENTIALS,
            model=TEXT_MODEL,
            texts=["hello"],
            base_address=BASE_ADDRESS,
        )

    assert result == ([[0.1, 0.2, 0.3]], 7)
    assert "session" not in call.call_args.kwargs


def test_multimodal_embedding_call_uses_sdk_managed_session_through_text_path() -> None:
    with patch.object(
        te.dashscope.MultiModalEmbedding, "call", return_value=_MultiModalResponse()
    ) as call:
        result = TongyiTextEmbeddingModel.embed_documents(
            credentials_kwargs=CREDENTIALS,
            model=MULTIMODAL_MODEL,
            texts=["hello"],
            base_address=BASE_ADDRESS,
        )

    assert result == ([[0.4, 0.5]], 5)
    assert "session" not in call.call_args.kwargs


def test_text_batches_delegate_session_management_to_sdk() -> None:
    model = _model(max_chunks=2)
    batches: list[list[str]] = []

    def embed_documents(**kwargs):
        assert "session" not in kwargs
        batches.append(kwargs["texts"])
        return ([[0.1]] * len(kwargs["texts"]), len(kwargs["texts"]))

    with patch.object(
        te.requests,
        "Session",
        side_effect=AssertionError("the plugin must not create a requests.Session"),
    ), patch.object(model, "embed_documents", side_effect=embed_documents):
        result = model._invoke(
            model=TEXT_MODEL, credentials=CREDENTIALS, texts=["one", "two", "three"]
        )

    assert result.embeddings == [[0.1], [0.1], [0.1]]
    assert batches == [["one", "two"], ["three"]]


def test_multimodal_invoke_delegates_session_management_to_sdk() -> None:
    model = _model()
    documents = [MultiModalContent(content_type=MultiModalContentType.TEXT, content="hello")]

    with patch.object(
        te.requests,
        "Session",
        side_effect=AssertionError("the plugin must not create a requests.Session"),
    ), patch.object(
        model, "embed_multimodal_documents", return_value=([[0.4, 0.5]], 5)
    ) as embed_multimodal_documents:
        result = model._invoke_multimodal(
            model=MULTIMODAL_MODEL, credentials=CREDENTIALS, documents=documents
        )

    assert result.embeddings == [[0.4, 0.5]]
    assert "session" not in embed_multimodal_documents.call_args.kwargs


def test_validate_credentials_delegates_session_management_to_sdk() -> None:
    model = _model()

    with patch.object(
        te.requests,
        "Session",
        side_effect=AssertionError("the plugin must not create a requests.Session"),
    ), patch.object(model, "embed_documents", return_value=([[0.1]], 1)) as embed_documents:
        model.validate_credentials(TEXT_MODEL, CREDENTIALS)

    assert "session" not in embed_documents.call_args.kwargs
