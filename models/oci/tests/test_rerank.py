"""Offline tests for OCIRerankModel: request shaping, index/score mapping, batching,
top_n / score_threshold handling and OCI error normalisation. No network access."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import oci
import pytest
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models.rerank.rerank import OCIRerankModel  # noqa: E402

MODEL = "cohere.rerank-v4.0-fast"
CREDENTIALS = {"authentication_method": "instance_principal_authentication", "compartment_ocid": "ocid1.compartment.oc1..example"}


def _rank(index: int, score: float, text: str | None = None):
    rank = {"index": index, "relevanceScore": score}
    if text:
        rank["document"] = {"text": text}
    return rank


def _response(ranks):
    payload = {"id": "req", "modelId": MODEL, "documentRanks": ranks}
    return SimpleNamespace(data=SimpleNamespace(text=json.dumps(payload)))


def _sent_body(client) -> dict:
    return json.loads(client.base_client.call_api.call_args.kwargs["body"])


@pytest.fixture
def model():
    return OCIRerankModel(model_schemas=[])


@pytest.fixture
def client(model):
    """Real BaseClient (genuine request serialisation) with the HTTP call stubbed."""
    with patch("oci.config.validate_config"), patch("oci.base_client.validate_config", create=True):
        base_client = oci.base_client.BaseClient(
            "generative_ai_inference", {"region": "us-chicago-1"}, MagicMock(),
            oci.generative_ai_inference.models.generative_ai_inference_type_mapping,
        )
    base_client.call_api = MagicMock()
    fake = SimpleNamespace(base_client=base_client)
    with patch.object(OCIRerankModel, "_create_client", return_value=fake):
        yield fake


def test_empty_docs_short_circuit_without_client(model):
    with patch.object(OCIRerankModel, "_create_client") as create:
        result = model.invoke(MODEL, CREDENTIALS, "q", [])
    assert result.docs == []
    create.assert_not_called()


def test_request_shape_and_result_mapping(model, client):
    docs = ["nevada", "washington dc", "saipan"]
    client.base_client.call_api.return_value = _response([_rank(1, 0.9), _rank(0, 0.4), _rank(2, 0.1)])

    result = model.invoke(MODEL, CREDENTIALS, "capital of the US?", docs)

    call = client.base_client.call_api.call_args.kwargs
    assert call["resource_path"] == "/actions/rerankText"
    assert call["method"] == "POST"
    assert call["header_params"]["content-type"] == "application/json"
    body = json.loads(call["body"])
    assert body == {
        "input": "capital of the US?",
        "compartmentId": CREDENTIALS["compartment_ocid"],
        "servingMode": {"servingType": "ON_DEMAND", "modelId": MODEL},
        "documents": docs,
        "isEcho": False,
    }

    assert [(d.index, d.text, d.score) for d in result.docs] == [
        (1, "washington dc", 0.9),
        (0, "nevada", 0.4),
        (2, "saipan", 0.1),
    ]
    assert result.model == MODEL


def test_top_n_is_forwarded_and_applied(model, client):
    client.base_client.call_api.return_value = _response([_rank(1, 0.9), _rank(0, 0.4)])
    result = model.invoke(MODEL, CREDENTIALS, "q", ["a", "b", "c"], top_n=2)
    assert _sent_body(client)["topN"] == 2
    assert [d.index for d in result.docs] == [1, 0]


def test_top_n_larger_than_docs_is_clamped(model, client):
    client.base_client.call_api.return_value = _response([_rank(0, 0.5)])
    model.invoke(MODEL, CREDENTIALS, "q", ["only"], top_n=10)
    assert _sent_body(client)["topN"] == 1


def test_score_threshold_filters(model, client):
    client.base_client.call_api.return_value = _response([_rank(1, 0.9), _rank(0, 0.4), _rank(2, 0.1)])
    result = model.invoke(MODEL, CREDENTIALS, "q", ["a", "b", "c"], score_threshold=0.4)
    assert [d.index for d in result.docs] == [1, 0]


def test_batches_above_oci_document_limit_and_merges_by_score(model, client):
    docs = [f"doc {i}" for i in range(OCIRerankModel.MAX_DOCUMENTS_PER_REQUEST + 5)]
    client.base_client.call_api.side_effect = [
        _response([_rank(3, 0.2), _rank(0, 0.1)]),  # first batch (offset 0)
        _response([_rank(2, 0.95), _rank(4, 0.5)]),  # second batch (offset 1000)
    ]
    result = model.invoke(MODEL, CREDENTIALS, "q", docs, top_n=3)

    assert client.base_client.call_api.call_count == 2
    first, second = (json.loads(c.kwargs["body"]) for c in client.base_client.call_api.call_args_list)
    assert len(first["documents"]) == OCIRerankModel.MAX_DOCUMENTS_PER_REQUEST
    assert len(second["documents"]) == 5
    # indexes are shifted back into the caller's list and merged in score order
    assert [(d.index, d.text, d.score) for d in result.docs] == [
        (1002, "doc 1002", 0.95),
        (1004, "doc 1004", 0.5),
        (3, "doc 3", 0.2),
    ]


def test_out_of_range_index_is_a_bad_request(model, client):
    client.base_client.call_api.return_value = _response([_rank(7, 0.9)])
    with pytest.raises(InvokeBadRequestError):
        model.invoke(MODEL, CREDENTIALS, "q", ["a", "b"])


def test_malformed_payload_is_a_bad_request(model, client):
    client.base_client.call_api.return_value = SimpleNamespace(data=SimpleNamespace(text="<html>oops</html>"))
    with pytest.raises(InvokeBadRequestError, match="invalid API response"):
        model.invoke(MODEL, CREDENTIALS, "q", ["a"])


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, InvokeAuthorizationError), (403, InvokeAuthorizationError), (429, InvokeRateLimitError),
     (500, InvokeServerUnavailableError), (400, InvokeBadRequestError), (404, InvokeBadRequestError)],
)
def test_oci_service_errors_are_normalised(model, client, status, expected):
    client.base_client.call_api.side_effect = oci.exceptions.ServiceError(status, "Code", {}, "boom")
    with pytest.raises(expected):
        model.invoke(MODEL, CREDENTIALS, "q", ["a"])


def test_validate_credentials_wraps_failures(model):
    with patch.object(OCIRerankModel, "_create_client", side_effect=RuntimeError("no network")):
        with pytest.raises(CredentialsValidateFailedError):
            model.validate_credentials(MODEL, CREDENTIALS)


def test_api_key_credentials_require_every_field(model):
    creds = {"authentication_method": "api_key_authentication", "key_content": "x"}
    with pytest.raises(CredentialsValidateFailedError, match="tenancy_ocid"):
        model._get_oci_credentials(creds)


def test_unknown_auth_method_is_rejected(model):
    with pytest.raises(CredentialsValidateFailedError, match="unsupported authentication_method"):
        model._get_oci_credentials({"authentication_method": "something_else"})
