import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from dify_plugin.entities.model.text_embedding import (
    EmbeddingUsage,
    MultiModalContent,
    MultiModalContentType,
)
from dify_plugin.errors.model import CredentialsValidateFailedError

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


class _RateLimitedResponse:
    def __init__(self) -> None:
        self.status_code = 429
        self.output = None
        self.usage = None


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


def _invoke(model: TongyiTextEmbeddingModel, texts: list[str] | None = None):
    return model._invoke(
        model=TEXT_MODEL,
        credentials=CREDENTIALS,
        texts=texts or ["hello"],
    )


def test_text_embedding_call_receives_session() -> None:
    session = MagicMock(spec=requests.Session)
    with patch.object(te.dashscope.TextEmbedding, "call", return_value=_TextResponse()) as call:
        result = TongyiTextEmbeddingModel.embed_documents(
            credentials_kwargs=CREDENTIALS,
            model=TEXT_MODEL,
            texts=["hello"],
            base_address=BASE_ADDRESS,
            session=session,
        )

    assert result == ([[0.1, 0.2, 0.3]], 7)
    assert call.call_args.kwargs["session"] is session


def test_multimodal_embedding_call_receives_session_through_text_path() -> None:
    session = MagicMock(spec=requests.Session)
    with patch.object(
        te.dashscope.MultiModalEmbedding,
        "call",
        return_value=_MultiModalResponse(),
    ) as call:
        result = TongyiTextEmbeddingModel.embed_documents(
            credentials_kwargs=CREDENTIALS,
            model=MULTIMODAL_MODEL,
            texts=["hello"],
            base_address=BASE_ADDRESS,
            session=session,
        )

    assert result == ([[0.4, 0.5]], 5)
    assert call.call_args.kwargs["session"] is session


def test_text_batches_reuse_one_session_and_close_it() -> None:
    model = _model(max_chunks=2)
    session = MagicMock(spec=requests.Session)
    batches = []

    def embed_documents(**kwargs):
        batches.append((kwargs["texts"], kwargs["session"]))
        return ([[0.1]] * len(kwargs["texts"]), len(kwargs["texts"]))

    with patch.object(
        te.requests, "Session", return_value=session
    ) as session_factory, patch.object(
        model,
        "embed_documents",
        side_effect=embed_documents,
    ):
        result = _invoke(model, ["one", "two", "three"])

    assert result.embeddings == [[0.1], [0.1], [0.1]]
    assert [batch for batch, _ in batches] == [["one", "two"], ["three"]]
    assert [batch_session for _, batch_session in batches] == [session, session]
    model._calc_response_usage.assert_called_once_with(
        model=TEXT_MODEL,
        credentials=CREDENTIALS,
        tokens=3,
    )
    session_factory.assert_called_once_with()
    session.close.assert_called_once_with()


def test_each_text_invocation_gets_an_isolated_session() -> None:
    model = _model()
    first, second = MagicMock(spec=requests.Session), MagicMock(spec=requests.Session)

    with patch.object(te.requests, "Session", side_effect=[first, second]), patch.object(
        model,
        "embed_documents",
        return_value=([[0.1]], 1),
    ) as embed_documents:
        _invoke(model)
        _invoke(model)

    assert [item.kwargs["session"] for item in embed_documents.call_args_list] == [first, second]
    first.close.assert_called_once_with()
    second.close.assert_called_once_with()


def test_multimodal_documents_reuse_one_session_and_close_it() -> None:
    model = _model()
    session = MagicMock(spec=requests.Session)
    documents = [
        MultiModalContent(content_type=MultiModalContentType.TEXT, content="one"),
        MultiModalContent(content_type=MultiModalContentType.TEXT, content="two"),
    ]

    with patch.object(te.requests, "Session", return_value=session), patch.object(
        te.dashscope.MultiModalEmbedding,
        "call",
        return_value=_MultiModalResponse(),
    ) as call:
        result = model._invoke_multimodal(
            model=MULTIMODAL_MODEL,
            credentials=CREDENTIALS,
            documents=documents,
        )

    assert result.embeddings == [[0.4, 0.5], [0.4, 0.5]]
    assert [item.kwargs["session"] for item in call.call_args_list] == [session, session]
    model._calc_response_usage.assert_called_once_with(
        model=MULTIMODAL_MODEL,
        credentials=CREDENTIALS,
        tokens=10,
    )
    session.close.assert_called_once_with()


def test_retry_reuses_session_and_closes_it(monkeypatch) -> None:
    model = _model()
    session = MagicMock(spec=requests.Session)
    error = requests.exceptions.ConnectionError("connection dropped")
    sleeps = []
    monkeypatch.setattr(te.time, "sleep", sleeps.append)

    with patch.object(te.requests, "Session", return_value=session), patch.object(
        te.dashscope.TextEmbedding,
        "call",
        side_effect=[error, _TextResponse()],
    ) as call:
        assert _invoke(model).embeddings == [[0.1, 0.2, 0.3]]

    assert [item.kwargs["session"] for item in call.call_args_list] == [session, session]
    assert sleeps == [1]
    session.close.assert_called_once_with()


def test_rate_limit_retry_reuses_session_and_closes_it(monkeypatch) -> None:
    model = _model()
    session = MagicMock(spec=requests.Session)
    sleeps = []
    monkeypatch.setattr(te.time, "sleep", sleeps.append)

    with patch.object(te.requests, "Session", return_value=session), patch.object(
        te.dashscope.TextEmbedding,
        "call",
        side_effect=[_RateLimitedResponse(), _TextResponse()],
    ) as call:
        assert _invoke(model).embeddings == [[0.1, 0.2, 0.3]]

    assert [item.kwargs["session"] for item in call.call_args_list] == [session, session]
    assert sleeps == [10]
    session.close.assert_called_once_with()


def test_persistent_connection_error_closes_session(monkeypatch) -> None:
    model = _model()
    session = MagicMock(spec=requests.Session)
    error = requests.exceptions.ConnectionError("connection dropped")
    sleeps = []
    monkeypatch.setattr(te.time, "sleep", sleeps.append)

    with patch.object(te.requests, "Session", return_value=session), patch.object(
        te.dashscope.TextEmbedding,
        "call",
        side_effect=error,
    ) as call, pytest.raises(requests.exceptions.ConnectionError) as exc_info:
        _invoke(model)

    assert exc_info.value is error
    assert [item.kwargs["session"] for item in call.call_args_list] == [session] * 3
    assert sleeps == [1, 3]
    session.close.assert_called_once_with()


def test_validate_credentials_closes_session_on_success() -> None:
    model = _model()
    session = MagicMock(spec=requests.Session)

    with patch.object(te.requests, "Session", return_value=session), patch.object(
        te.dashscope.TextEmbedding,
        "call",
        return_value=_TextResponse(),
    ) as call:
        model.validate_credentials(TEXT_MODEL, CREDENTIALS)

    assert call.call_args.kwargs["session"] is session
    session.close.assert_called_once_with()


def test_validate_credentials_closes_session_on_error() -> None:
    model = _model()
    session = MagicMock(spec=requests.Session)

    with patch.object(te.requests, "Session", return_value=session), patch.object(
        te.dashscope.TextEmbedding,
        "call",
        side_effect=ValueError("invalid response"),
    ), pytest.raises(CredentialsValidateFailedError, match="invalid response"):
        model.validate_credentials(TEXT_MODEL, CREDENTIALS)

    session.close.assert_called_once_with()
