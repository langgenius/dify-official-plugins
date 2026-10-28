from unittest.mock import patch

import pytest
from dify_plugin.entities.model import AIModelEntity, EmbeddingInputType

from models.text_embedding.text_embedding import TokenerTextEmbeddingModel


@pytest.mark.parametrize("model_id", ["gemini-embedding-001", "gemini-embedding-2-preview"])
@pytest.mark.parametrize("input_type", [EmbeddingInputType.QUERY, EmbeddingInputType.DOCUMENT])
def test_gemini_omits_unsupported_user_metadata_without_changing_input_contract(
    model_id, input_type
):
    schema = AIModelEntity.model_validate(
        {
            "model": model_id,
            "label": {"en_US": model_id},
            "model_type": "text-embedding",
            "model_properties": {"max_chunks": 2, "context_size": 2048},
            "pricing": {"input": "1", "unit": "0.000001", "currency": "USD"},
        }
    )
    instance = TokenerTextEmbeddingModel(model_schemas=[schema])
    texts = ["first", "second"]
    credentials = {"api_key": "unit-test-key"}
    body = {
        "data": [{"index": 1, "embedding": [0.3, 0.4]}, {"index": 0, "embedding": [0.1, 0.2]}],
        "usage": {"total_tokens": 3},
    }
    with patch.object(instance, "_post", return_value=body) as post:
        result = instance.invoke(
            model_id, credentials, texts, user="console-user", input_type=input_type
        )
    payload = post.call_args.args[2]
    with patch.object(instance, "_post", return_value=body) as without_user:
        instance.invoke(model_id, credentials, texts, user=None, input_type=input_type)
    # Adding a Dify console identity must not change this model's existing
    # query/document formatting contract or introduce upstream-only metadata.
    assert payload == without_user.call_args.args[2]
    assert "user" not in payload
    assert payload["model"] == model_id
    assert payload["encoding_format"] == "float"
    if model_id == "gemini-embedding-001":
        assert payload["input"] == texts
    assert result.embeddings == [[0.1, 0.2], [0.3, 0.4]]
    assert texts == ["first", "second"]
    assert credentials == {"api_key": "unit-test-key"}


def test_openai_embedding_keeps_existing_user_metadata():
    schema = AIModelEntity.model_validate(
        {
            "model": "text-embedding-3-small",
            "label": {"en_US": "embedding"},
            "model_type": "text-embedding",
            "model_properties": {"max_chunks": 2, "context_size": 8192},
            "pricing": {"input": "1", "unit": "0.000001", "currency": "USD"},
        }
    )
    instance = TokenerTextEmbeddingModel(model_schemas=[schema])
    with patch.object(
        instance,
        "_post",
        return_value={
            "data": [{"index": 0, "embedding": [0.1]}],
            "usage": {"total_tokens": 1},
        },
    ) as post:
        instance.invoke(
            "text-embedding-3-small", {"api_key": "unit-test-key"}, ["input"], user="console-user"
        )
    assert post.call_args.args[2]["user"] == "console-user"
