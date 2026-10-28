"""Response-index compatibility only; these mocks do not certify RAG quality."""

from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity, EmbeddingInputType
from dify_plugin.errors.model import InvokeServerUnavailableError

from models.text_embedding.text_embedding import TokenerTextEmbeddingModel

MODEL_IDS = [
    "text-embedding-3-small",
    "text-embedding-3-large",
    "text-embedding-ada-002",
    "gemini-embedding-001",
    "gemini-embedding-2-preview",
]


def runtime(model_id="text-embedding-3-small"):
    schema = AIModelEntity.model_validate(
        yaml.safe_load(Path(f"models/text_embedding/{model_id}.yaml").read_text())
    )
    return TokenerTextEmbeddingModel(model_schemas=[schema])


@pytest.mark.parametrize("model_id", MODEL_IDS)
@pytest.mark.parametrize("input_type", [EmbeddingInputType.QUERY, EmbeddingInputType.DOCUMENT])
def test_single_explicit_null_index_does_not_change_public_input_contract(model_id, input_type):
    instance = runtime(model_id)
    body = {"data": [{"index": None, "embedding": [0.1, 0.2]}], "usage": {"total_tokens": 3}}
    original = deepcopy(body)
    with patch.object(instance, "_post", return_value=body) as post:
        result = instance.invoke(
            model_id,
            {"api_key": "OFFLINE_ONLY"},
            ["same input"],
            user="offline-user",
            input_type=input_type,
        )
    assert result.embeddings == [[0.1, 0.2]]
    assert result.usage.total_tokens == 3
    assert body == original  # Do not mutate the decoded upstream response.
    assert post.call_count == 1
    payload = post.call_args.args[2]
    assert payload["model"] == model_id
    expected = "same input"
    if model_id == "gemini-embedding-2-preview":
        prefix = (
            "task: search result | query: "
            if input_type == EmbeddingInputType.QUERY
            else "title: none | text: "
        )
        expected = prefix + expected
    assert payload["input"] == [expected]
    assert payload["encoding_format"] == "float"
    if model_id.startswith("gemini-"):
        assert "user" not in payload
    else:
        assert payload["user"] == "offline-user"


@pytest.mark.parametrize("index", [False, True, "0", 0.0, -1, 1, [], {}])
def test_single_other_invalid_indices_are_never_inferred(index):
    instance = runtime()
    body = {"data": [{"index": index, "embedding": [0.1]}], "usage": {"total_tokens": 1}}
    with (
        patch.object(instance, "_post", return_value=body),
        pytest.raises(InvokeServerUnavailableError, match="invalid embedding indices"),
    ):
        instance.invoke("text-embedding-3-small", {"api_key": "OFFLINE_ONLY"}, ["input"])


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        [],
        [None],
        [1],
        ["result"],
        [[0, 0.1]],
        [{"embedding": [0.1]}],
        [{"index": None, "embedding": [0.1]}, {"index": 1, "embedding": [0.2]}],
    ],
)
def test_single_malformed_or_missing_index_shape_is_rejected(data):
    instance = runtime()
    body = {"data": data, "usage": {"total_tokens": 1}}
    with (
        patch.object(instance, "_post", return_value=body),
        pytest.raises(InvokeServerUnavailableError, match="invalid embedding indices"),
    ):
        instance.invoke("text-embedding-3-small", {"api_key": "OFFLINE_ONLY"}, ["input"])


@pytest.mark.parametrize(
    "data",
    [
        [{"index": None, "embedding": [0.1]}],
        [{"index": None, "embedding": [0.1]}, {"index": None, "embedding": [0.2]}],
        [{"index": None, "embedding": [0.1]}, {"index": 1, "embedding": [0.2]}],
        [{"index": 0, "embedding": [0.1]}, {"index": None, "embedding": [0.2]}],
        [{"index": 0, "embedding": [0.1]}, {"index": 0, "embedding": [0.2]}],
        [{"index": 0, "embedding": [0.1]}, {"embedding": [0.2]}],
    ],
)
def test_batch_null_duplicate_or_missing_indices_remain_errors(data):
    instance = runtime()
    body = {"data": data, "usage": {"total_tokens": 2}}
    with (
        patch.object(instance, "_post", return_value=body),
        pytest.raises(InvokeServerUnavailableError, match="invalid embedding indices"),
    ):
        instance.invoke("text-embedding-3-small", {"api_key": "OFFLINE_ONLY"}, ["first", "second"])


def test_single_remainder_batch_null_index_does_not_guess_order_of_previous_batch():
    instance = runtime()
    responses = [
        {
            "data": [{"index": 1, "embedding": [0.2]}, {"index": 0, "embedding": [0.1]}],
            "usage": {"total_tokens": 2},
        },
        {"data": [{"index": None, "embedding": [0.3]}], "usage": {"total_tokens": 1}},
    ]
    with (
        patch.object(instance, "_get_max_chunks", return_value=2),
        patch.object(instance, "_post", side_effect=responses) as post,
    ):
        result = instance.invoke(
            "text-embedding-3-small", {"api_key": "OFFLINE_ONLY"}, ["first", "second", "third"]
        )
    assert result.embeddings == [[0.1], [0.2], [0.3]]
    assert result.usage.total_tokens == 3
    assert post.call_count == 2
    assert responses[1]["data"][0]["index"] is None


@pytest.mark.parametrize("vector", [[], None, [True], [float("nan")], [float("inf")]])
def test_index_compatibility_does_not_relax_vector_validation(vector):
    instance = runtime()
    body = {"data": [{"index": None, "embedding": vector}], "usage": {"total_tokens": 1}}
    with (
        patch.object(instance, "_post", return_value=body),
        pytest.raises(InvokeServerUnavailableError, match="invalid embedding vectors"),
    ):
        instance.invoke("text-embedding-3-small", {"api_key": "OFFLINE_ONLY"}, ["input"])


@pytest.mark.parametrize("used", [None, True, -1, "1"])
def test_index_compatibility_does_not_relax_usage_validation(used):
    instance = runtime()
    body = {"data": [{"index": None, "embedding": [0.1]}], "usage": {"total_tokens": used}}
    with (
        patch.object(instance, "_post", return_value=body),
        pytest.raises(InvokeServerUnavailableError, match="invalid embedding usage"),
    ):
        instance.invoke("text-embedding-3-small", {"api_key": "OFFLINE_ONLY"}, ["input"])
