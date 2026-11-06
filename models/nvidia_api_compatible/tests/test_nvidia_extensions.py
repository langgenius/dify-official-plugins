"""Tests for the NVIDIA-specific additions: input_type mapping, truncate/modality/
dimensions, Extra Body JSON, and the NVIDIA rerank format."""

import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from dify_plugin.entities.model import EmbeddingInputType
from dify_plugin.entities.model.llm import LLMResult, LLMUsage
from dify_plugin.entities.model.message import AssistantPromptMessage, UserPromptMessage
from dify_plugin.entities.model.text_embedding import (
    MultiModalContent,
    MultiModalContentType,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
    InvokeError,
    InvokeServerUnavailableError,
)

from models.common_openai import merge_extra_body, parse_extra_body
from models.llm.llm import OpenAILargeLanguageModel
from models.rerank.rerank import OpenAIRerankModel
from models.text_embedding.text_embedding import OpenAITextEmbeddingModel

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _response(status_code=200, json_data=None, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data
    response.text = text
    return response


# --------------------------------------------------------------------------- #
# Extra Body
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_extra_body_empty_returns_empty_dict(raw):
    assert parse_extra_body({"extra_body": raw}) == {}
    assert parse_extra_body({}) == {}


def test_extra_body_parses_json_object():
    assert parse_extra_body({"extra_body": '{"truncate": "END", "nvext": {"top_k": 5}}'}) == {
        "truncate": "END",
        "nvext": {"top_k": 5},
    }


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("{not json", "not valid JSON"),
        ("[1, 2]", "must be a JSON object"),
        ('{"model": "x"}', "reserved keys: model"),
        ('{"input": [], "stream": true}', "reserved keys: input, stream"),
    ],
)
def test_extra_body_rejects_invalid_values(raw, message):
    with pytest.raises(ValueError, match=message):
        parse_extra_body({"extra_body": raw})


def test_merge_extra_body_overrides_existing_fields():
    payload = {"model": "m", "truncate": "NONE"}
    merge_extra_body(payload, {"extra_body": '{"truncate": "END"}'})
    assert payload == {"model": "m", "truncate": "END"}


# --------------------------------------------------------------------------- #
# Text embedding
# --------------------------------------------------------------------------- #


def _embedding_credentials(**overrides):
    credentials = {
        "endpoint_url": "https://integrate.api.nvidia.com/v1/",
        "api_key": "test-key",
        "context_size": "32768",
        "max_chunks": "16",
        "encoding_format": "float",
        "input_type_document": "passage",
        "input_type_query": "query",
        "truncate": "END",
        "modality": "not_set",
        "dimensions": "",
        "extra_body": "",
    }
    credentials.update(overrides)
    return credentials


def _embedding_ok(n=1, reverse=False):
    items = [{"index": i, "embedding": [float(i)]} for i in range(n)]
    if reverse:
        items.reverse()
    return _response(json_data={"data": items, "usage": {"prompt_tokens": n}})


@pytest.mark.parametrize(
    ("input_type", "expected"),
    [(EmbeddingInputType.DOCUMENT, "passage"), (EmbeddingInputType.QUERY, "query")],
)
@patch("models.text_embedding.text_embedding.requests.post")
def test_embedding_maps_dify_input_type_to_configured_value(mock_post, input_type, expected):
    mock_post.return_value = _embedding_ok()
    model = OpenAITextEmbeddingModel(model_schemas=[])

    model._invoke(
        model="nvidia/nemotron-3.5-embed-8b",
        credentials=_embedding_credentials(),
        texts=["hello"],
        input_type=input_type,
    )

    assert mock_post.call_args.args[0] == "https://integrate.api.nvidia.com/v1/embeddings"
    assert mock_post.call_args.kwargs["json"] == {
        "model": "nvidia/nemotron-3.5-embed-8b",
        "input": ["hello"],
        "encoding_format": "float",
        "input_type": expected,
        "truncate": "END",
    }


@patch("models.text_embedding.text_embedding.requests.post")
def test_embedding_omits_empty_optional_fields(mock_post):
    mock_post.return_value = _embedding_ok()
    model = OpenAITextEmbeddingModel(model_schemas=[])

    model._invoke(
        model="m",
        credentials=_embedding_credentials(
            input_type_document="", truncate="not_set", encoding_format="not_set"
        ),
        texts=["hello"],
    )

    assert mock_post.call_args.kwargs["json"] == {"model": "m", "input": ["hello"]}


@patch("models.text_embedding.text_embedding.requests.post")
def test_embedding_sends_modality_dimensions_and_extra_body(mock_post):
    mock_post.return_value = _embedding_ok()
    model = OpenAITextEmbeddingModel(model_schemas=[])

    model._invoke(
        model="m",
        credentials=_embedding_credentials(
            modality="text",
            dimensions="1024",
            extra_body='{"truncate": "START", "user_tag": "kb"}',
        ),
        texts=["hello"],
    )

    payload = mock_post.call_args.kwargs["json"]
    assert payload["modality"] == "text"
    assert payload["dimensions"] == 1024
    assert payload["truncate"] == "START"  # Extra Body wins
    assert payload["user_tag"] == "kb"


@patch("models.text_embedding.text_embedding.requests.post")
def test_embedding_rejects_invalid_dimensions(mock_post):
    model = OpenAITextEmbeddingModel(model_schemas=[])
    with pytest.raises(InvokeError, match="Dimensions must be an integer"):
        model._invoke(model="m", credentials=_embedding_credentials(dimensions="abc"), texts=["x"])
    mock_post.assert_not_called()


@patch("models.text_embedding.text_embedding.requests.post")
def test_embedding_batches_by_max_chunks_and_keeps_order(mock_post):
    mock_post.side_effect = [_embedding_ok(2, reverse=True), _embedding_ok(1)]
    model = OpenAITextEmbeddingModel(model_schemas=[])

    result = model._invoke(
        model="m", credentials=_embedding_credentials(max_chunks="2"), texts=["a", "b", "c"]
    )

    assert mock_post.call_count == 2
    assert mock_post.call_args_list[0].kwargs["json"]["input"] == ["a", "b"]
    assert mock_post.call_args_list[1].kwargs["json"]["input"] == ["c"]
    # First batch came back reversed; result must follow input order.
    assert result.embeddings == [[0.0], [1.0], [0.0]]
    assert result.usage.tokens == 3


@patch("models.text_embedding.text_embedding.requests.post")
def test_embedding_error_includes_provider_message(mock_post):
    mock_post.return_value = _response(
        status_code=400, text='{"detail": "input_type is required for asymmetric models"}'
    )
    model = OpenAITextEmbeddingModel(model_schemas=[])

    with pytest.raises(InvokeError, match="HTTP 400.*input_type is required"):
        model._invoke(model="m", credentials=_embedding_credentials(), texts=["x"])


@patch("models.text_embedding.text_embedding.requests.post")
def test_embedding_multimodal_text_path_also_sends_input_type(mock_post):
    mock_post.return_value = _embedding_ok()
    model = OpenAITextEmbeddingModel(model_schemas=[])

    model._invoke_multimodal(
        model="m",
        credentials=_embedding_credentials(),
        documents=[MultiModalContent(content="hello", content_type=MultiModalContentType.TEXT)],
        input_type=EmbeddingInputType.QUERY,
    )

    assert mock_post.call_args.kwargs["json"]["input_type"] == "query"


# --------------------------------------------------------------------------- #
# Rerank (NVIDIA format)
# --------------------------------------------------------------------------- #

RERANK_URL = "https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-3_2-nv-rerankqa-1b-v2/reranking"


def _rerank_credentials(**overrides):
    credentials = {
        "endpoint_url": "https://integrate.api.nvidia.com/v1",
        "rerank_endpoint_url": RERANK_URL,
        "rerank_api_format": "nvidia",
        "rerank_truncate": "END",
        "api_key": "test-key",
        "context_size": "8192",
    }
    credentials.update(overrides)
    return credentials


@patch("models.rerank.rerank.requests.post")
def test_nvidia_rerank_payload_and_scores(mock_post):
    mock_post.return_value = _response(
        json_data={"rankings": [{"index": 2, "logit": 3.0}, {"index": 0, "logit": -1.0}, {"index": 1, "logit": 0.0}]}
    )
    model = OpenAIRerankModel(model_schemas=[])

    result = model._invoke(
        model="nvidia/llama-3.2-nv-rerankqa-1b-v2",
        credentials=_rerank_credentials(),
        query="q",
        docs=["d0", "d1", "d2"],
    )

    assert mock_post.call_args.args[0] == RERANK_URL
    assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert mock_post.call_args.kwargs["json"] == {
        "model": "nvidia/llama-3.2-nv-rerankqa-1b-v2",
        "query": {"text": "q"},
        "passages": [{"text": "d0"}, {"text": "d1"}, {"text": "d2"}],
        "truncate": "END",
    }
    assert [d.index for d in result.docs] == [2, 1, 0]
    assert [d.text for d in result.docs] == ["d2", "d1", "d0"]
    assert result.docs[0].score == pytest.approx(1 / (1 + math.exp(-3.0)))
    assert result.docs[1].score == pytest.approx(0.5)


@patch("models.rerank.rerank.requests.post")
def test_nvidia_rerank_applies_top_n_and_threshold(mock_post):
    mock_post.return_value = _response(
        json_data={"rankings": [{"index": 0, "logit": 2.0}, {"index": 1, "logit": 0.1}, {"index": 2, "logit": -3.0}]}
    )
    model = OpenAIRerankModel(model_schemas=[])

    result = model._invoke(
        model="m", credentials=_rerank_credentials(), query="q", docs=["a", "b", "c"],
        top_n=2, score_threshold=0.6,
    )

    assert [d.index for d in result.docs] == [0]


@patch("models.rerank.rerank.requests.post")
def test_nvidia_rerank_defaults_to_ranking_path_and_omits_unset_truncate(mock_post):
    mock_post.return_value = _response(json_data={"rankings": []})
    model = OpenAIRerankModel(model_schemas=[])

    model._invoke(
        model="m",
        credentials=_rerank_credentials(
            rerank_endpoint_url="", rerank_truncate="not_set", endpoint_url="http://nim:8000/v1/"
        ),
        query="q",
        docs=["a"],
    )

    assert mock_post.call_args.args[0] == "http://nim:8000/v1/ranking"
    assert "truncate" not in mock_post.call_args.kwargs["json"]


@patch("models.rerank.rerank.requests.post")
def test_nvidia_rerank_error_includes_provider_message(mock_post):
    mock_post.return_value = _response(status_code=404, text='{"detail": "Function not found"}')
    model = OpenAIRerankModel(model_schemas=[])

    with pytest.raises(InvokeServerUnavailableError, match="HTTP 404.*Function not found"):
        model._invoke(model="m", credentials=_rerank_credentials(), query="q", docs=["a"])


@patch("models.rerank.rerank.requests.post")
def test_nvidia_rerank_rejects_bad_extra_body_before_request(mock_post):
    model = OpenAIRerankModel(model_schemas=[])
    with pytest.raises(InvokeBadRequestError, match="reserved keys: passages"):
        model._invoke(
            model="m", credentials=_rerank_credentials(extra_body='{"passages": []}'),
            query="q", docs=["a"],
        )
    mock_post.assert_not_called()


@patch("models.rerank.rerank.requests.post")
def test_nvidia_rerank_multimodal_text_only_delegates(mock_post):
    mock_post.return_value = _response(json_data={"rankings": [{"index": 0, "logit": 1.0}]})
    model = OpenAIRerankModel(model_schemas=[])

    result = model._invoke_multimodal(
        model="m",
        credentials=_rerank_credentials(),
        query=MultiModalContent(content="q", content_type=MultiModalContentType.TEXT),
        docs=[MultiModalContent(content="a", content_type=MultiModalContentType.TEXT)],
    )

    assert mock_post.call_args.kwargs["json"]["passages"] == [{"text": "a"}]
    assert result.docs[0].text == "a"


def test_nvidia_rerank_multimodal_rejects_images():
    model = OpenAIRerankModel(model_schemas=[])
    with pytest.raises(InvokeBadRequestError, match="does not support images"):
        model._invoke_multimodal(
            model="m",
            credentials=_rerank_credentials(),
            query=MultiModalContent(content="q", content_type=MultiModalContentType.TEXT),
            docs=[MultiModalContent(content="aGVsbG8=", content_type=MultiModalContentType.IMAGE)],
        )


@patch("models.rerank.rerank.requests.post")
def test_cohere_rerank_format_still_supported_with_extra_body(mock_post):
    mock_post.return_value = _response(json_data={"results": [{"index": 0, "relevance_score": 0.9}]})
    model = OpenAIRerankModel(model_schemas=[])

    model._invoke(
        model="m",
        credentials=_rerank_credentials(
            rerank_api_format="cohere", rerank_endpoint_url="", extra_body='{"return_documents": false}'
        ),
        query="q",
        docs=["a"],
    )

    assert mock_post.call_args.args[0] == "https://integrate.api.nvidia.com/v1/rerank"
    assert mock_post.call_args.kwargs["json"] == {
        "model": "m", "query": "q", "documents": ["a"], "top_n": 1, "return_documents": False,
    }


# --------------------------------------------------------------------------- #
# LLM
# --------------------------------------------------------------------------- #

BASE_INVOKE = "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke"
LLM_CREDENTIALS = {
    "endpoint_url": "https://integrate.api.nvidia.com/v1",
    "api_key": "test-key",
    "mode": "chat",
}


def _invoke_llm(credentials, model_parameters):
    llm = OpenAILargeLanguageModel(model_schemas=[])
    stub = LLMResult(
        model="m", prompt_messages=[], message=AssistantPromptMessage(content="ok"),
        usage=LLMUsage.empty_usage(),
    )
    with patch(BASE_INVOKE, return_value=stub) as base_invoke:
        llm._invoke(
            model="meta/llama-3.1-8b-instruct",
            credentials=credentials,
            prompt_messages=[UserPromptMessage(content="hi")],
            model_parameters=model_parameters,
            stream=False,
        )
    return base_invoke.call_args.args[3]


def test_llm_merges_extra_body_into_parameters():
    params = _invoke_llm(
        {**LLM_CREDENTIALS, "extra_body": '{"nvext": {"top_k": 1}, "temperature": 0.1}'},
        {"temperature": 0.7},
    )
    assert params["nvext"] == {"top_k": 1}
    assert params["temperature"] == 0.1


def test_llm_without_extra_body_is_unchanged():
    params = _invoke_llm(dict(LLM_CREDENTIALS), {"temperature": 0.7})
    assert params == {"temperature": 0.7}


def test_llm_invalid_extra_body_raises():
    with pytest.raises(InvokeError, match="not valid JSON"):
        _invoke_llm({**LLM_CREDENTIALS, "extra_body": "{bad"}, {})


def test_llm_validate_credentials_rejects_invalid_extra_body():
    llm = OpenAILargeLanguageModel(model_schemas=[])
    with pytest.raises(CredentialsValidateFailedError, match="reserved keys: messages"):
        llm.validate_credentials("m", {**LLM_CREDENTIALS, "extra_body": '{"messages": []}'})


# --------------------------------------------------------------------------- #
# Provider schema
# --------------------------------------------------------------------------- #


def test_provider_schema_only_exposes_llm_embedding_rerank():
    schema = yaml.safe_load(
        (PLUGIN_ROOT / "provider" / "nvidia_api_compatible.yaml").read_text(encoding="utf-8")
    )
    assert schema["provider"] == "nvidia_api_compatible"
    assert schema["supported_model_types"] == ["llm", "text-embedding", "rerank"]

    fields = schema["model_credential_schema"]["credential_form_schemas"]
    by_type: dict[str, set[str]] = {}
    for field in fields:
        types = [s["value"] for s in field.get("show_on", [])] or ["*"]
        for t in types:
            by_type.setdefault(t, set()).add(field["variable"])
        if field["type"] == "select":
            values = [o["value"] for o in field["options"]]
            assert field.get("default") in values, field["variable"]

    assert {"api_key", "endpoint_url", "extra_body"} <= by_type["*"]
    assert {"input_type_document", "input_type_query", "truncate", "modality", "dimensions"} <= by_type["text-embedding"]
    assert {"rerank_api_format", "rerank_truncate", "rerank_endpoint_url"} <= by_type["rerank"]
    assert not {"speech2text", "tts"} & set(by_type)

    for source in schema["extra"]["python"]["model_sources"] + [schema["extra"]["python"]["provider_source"]]:
        assert (PLUGIN_ROOT / source).is_file(), source


def test_embedding_schema_honours_max_chunks_credential():
    from dify_plugin.entities.model import ModelPropertyKey

    model = OpenAITextEmbeddingModel(model_schemas=[])
    schema = model.get_customizable_model_schema("m", {"context_size": "32768", "max_chunks": "16"})
    assert schema.model_properties[ModelPropertyKey.MAX_CHUNKS] == 16
    assert schema.model_properties[ModelPropertyKey.CONTEXT_SIZE] == 32768

    schema = model.get_customizable_model_schema("m", {"context_size": "512", "max_chunks": "abc"})
    assert schema.model_properties[ModelPropertyKey.MAX_CHUNKS] == 1


def test_provider_schema_fits_plugin_daemon_limit():
    # dify-plugin-daemon validates credential_form_schemas with `lte=32`;
    # more fields make the plugin fail to register ("failed on the 'lte' tag").
    schema = yaml.safe_load(
        (PLUGIN_ROOT / "provider" / "nvidia_api_compatible.yaml").read_text(encoding="utf-8")
    )
    assert len(schema["model_credential_schema"]["credential_form_schemas"]) <= 32


# --------------------------------------------------------------------------- #
# Embedding: retry and batch splitting on transient server errors
# --------------------------------------------------------------------------- #

SERVER_ERROR = '{"object":"error","message":"service inference failed","type":"server_error"}'


def _vectors_for(payload):
    """Return a 200 response with one vector per input, value = len(text)."""
    texts = payload["input"]
    return _embedding_ok_values([[float(len(t))] for t in texts])


def _embedding_ok_values(vectors):
    return _response(
        json_data={
            "data": [{"index": i, "embedding": v} for i, v in enumerate(vectors)],
            "usage": {"prompt_tokens": len(vectors)},
        }
    )


@patch("models.text_embedding.text_embedding.time.sleep")
@patch("models.text_embedding.text_embedding.requests.post")
def test_embedding_retries_transient_500_then_succeeds(mock_post, mock_sleep):
    mock_post.side_effect = [_response(500, text=SERVER_ERROR), _embedding_ok()]
    model = OpenAITextEmbeddingModel(model_schemas=[])

    result = model._invoke(model="m", credentials=_embedding_credentials(), texts=["a"])

    assert mock_post.call_count == 2
    assert mock_sleep.call_count == 1
    assert result.embeddings == [[0.0]]


@patch("models.text_embedding.text_embedding.time.sleep")
@patch("models.text_embedding.text_embedding.requests.post")
def test_embedding_splits_batch_when_server_keeps_failing(mock_post, mock_sleep):
    # Server fails for any batch with more than 2 texts, works for smaller ones.
    def fake_post(url, headers, json, timeout):
        if len(json["input"]) > 2:
            return _response(500, text=SERVER_ERROR)
        return _vectors_for(json)

    mock_post.side_effect = fake_post
    model = OpenAITextEmbeddingModel(model_schemas=[])
    texts = ["a", "bb", "ccc", "dddd", "eeeee"]

    result = model._invoke(model="m", credentials=_embedding_credentials(max_chunks="8"), texts=texts)

    assert result.embeddings == [[1.0], [2.0], [3.0], [4.0], [5.0]]
    assert result.usage.tokens == 5
    # input_type etc. are still sent on the split requests
    assert all(c.kwargs["json"]["input_type"] == "passage" for c in mock_post.call_args_list)


@patch("models.text_embedding.text_embedding.time.sleep")
@patch("models.text_embedding.text_embedding.requests.post")
def test_embedding_reports_failing_input_position(mock_post, mock_sleep):
    def fake_post(url, headers, json, timeout):
        if "BAD" in json["input"]:
            return _response(500, text=SERVER_ERROR)
        return _vectors_for(json)

    mock_post.side_effect = fake_post
    model = OpenAITextEmbeddingModel(model_schemas=[])

    with pytest.raises(InvokeError, match=r"HTTP 500 \(input #3, 3 characters\).*service inference failed"):
        model._invoke(
            model="m", credentials=_embedding_credentials(max_chunks="4"), texts=["a", "b", "BAD", "d"]
        )


@patch("models.text_embedding.text_embedding.time.sleep")
@patch("models.text_embedding.text_embedding.requests.post")
def test_embedding_does_not_retry_client_errors(mock_post, mock_sleep):
    mock_post.return_value = _response(400, text='{"detail": "bad"}')
    model = OpenAITextEmbeddingModel(model_schemas=[])

    with pytest.raises(InvokeError, match="HTTP 400"):
        model._invoke(model="m", credentials=_embedding_credentials(), texts=["a", "b"])
    assert mock_post.call_count == 1
    mock_sleep.assert_not_called()


@patch("models.text_embedding.text_embedding.time.sleep")
@patch("models.text_embedding.text_embedding.requests.post")
def test_embedding_single_long_input_survives_several_random_500s(mock_post, mock_sleep):
    # Mirrors the hosted NVIDIA behaviour: same text fails a few times, then works.
    mock_post.side_effect = [_response(500, text=SERVER_ERROR)] * 4 + [_embedding_ok()]
    model = OpenAITextEmbeddingModel(model_schemas=[])

    result = model._invoke(model="m", credentials=_embedding_credentials(), texts=["long text"])

    assert result.embeddings == [[0.0]]
    assert mock_post.call_count == 5
    assert [c.args[0] for c in mock_sleep.call_args_list] == [0.5, 1.0, 2.0, 3.0]


@patch("models.text_embedding.text_embedding.time.sleep")
@patch("models.text_embedding.text_embedding.requests.post")
def test_embedding_batch_retries_once_then_splits(mock_post, mock_sleep):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(len(json["input"]))
        if len(json["input"]) > 1:
            return _response(500, text=SERVER_ERROR)
        return _vectors_for(json)

    mock_post.side_effect = fake_post
    model = OpenAITextEmbeddingModel(model_schemas=[])

    model._invoke(model="m", credentials=_embedding_credentials(max_chunks="2"), texts=["a", "b"])

    assert calls == [2, 2, 1, 1]  # one retry for the batch, then split
