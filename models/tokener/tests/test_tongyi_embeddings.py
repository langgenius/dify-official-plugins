from decimal import Decimal

import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.text_embedding import MultiModalContent, MultiModalContentType
from dify_plugin.errors.model import InvokeBadRequestError, InvokeServerUnavailableError
from protocol_http import wire as wire

from models.text_embedding.text_embedding import TokenerTextEmbeddingModel
from scripts.sync_catalog import SOURCE_ROOT


def embedding(model_id):
    path = SOURCE_ROOT / "tongyi/models/text_embedding" / f"{model_id}.yaml"
    schema = AIModelEntity.model_validate(yaml.safe_load(path.read_text()))
    return TokenerTextEmbeddingModel(model_schemas=[schema])


def reply(tokens, text, image):
    return {
        "data": [{"index": 0, "embedding": [0.1, 0.2]}],
        "usage": {
            "total_tokens": tokens,
            "prompt_tokens_details": {"text_tokens": text, "image_tokens": image},
        },
    }


@pytest.mark.parametrize("model_id", ["qwen3-vl-embedding", "multimodal-embedding-v1"])
def test_public_text_keeps_source_single_document_requests(model_id, wire):
    _, calls, replies = wire
    replies.extend([(200, {}, reply(3, 3, 0)), (200, {}, reply(5, 5, 0))])
    result = embedding(model_id).invoke(model_id, {"api_key": "test-key"}, ["one", "two"])
    assert [call[2]["input"] for call in calls] == [[{"text": "one"}], [{"text": "two"}]]
    assert all(call[0] == "/v1/embeddings" for call in calls)
    assert result.embeddings == [[0.1, 0.2], [0.1, 0.2]]
    assert result.usage.total_tokens == 8


@pytest.mark.parametrize("model_id", ["qwen3-vl-embedding", "multimodal-embedding-v1"])
@pytest.mark.parametrize("image,mime", [("iVBORw0KGgo=", "png"), ("/9j/", "jpeg"), ("Qk0=", "bmp")])
def test_public_multimodal_preserves_physical_usage_and_source_price(model_id, image, mime, wire):
    _, calls, replies = wire
    replies.extend([(200, {}, reply(12, 12, 0)), (200, {}, reply(256, 0, 256))])
    model = embedding(model_id)
    documents = [
        MultiModalContent(content_type=MultiModalContentType.TEXT, content="hello"),
        MultiModalContent(content_type=MultiModalContentType.IMAGE, content=image),
    ]
    result = model.invoke_multimodal(model_id, {"api_key": "test-key"}, documents)
    assert [call[2]["input"] for call in calls] == [
        [{"text": "hello"}],
        [{"image": f"data:image/{mime};base64,{image}"}],
    ]
    assert result.usage.total_tokens == 268
    expected = Decimal("0.000067248") if model_id == "qwen3-vl-embedding" else Decimal("0.000134")
    assert result.usage.total_price == expected
    assert result.embeddings == [[0.1, 0.2], [0.1, 0.2]]


@pytest.mark.parametrize("fault", ["missing_vector", "missing_image_usage", "wrong_total"])
def test_multimodal_rejects_incomplete_upstream_contract(fault, wire):
    _, _, replies = wire
    body = reply(256, 0, 256)
    if fault == "missing_vector":
        body["data"] = []
    elif fault == "missing_image_usage":
        body["usage"].pop("prompt_tokens_details")
    else:
        body["usage"]["total_tokens"] = 300
    replies.append((200, {}, body))
    document = MultiModalContent(content_type=MultiModalContentType.IMAGE, content="iVBORw0KGgo=")
    with pytest.raises(InvokeServerUnavailableError):
        embedding("qwen3-vl-embedding").invoke_multimodal(
            "qwen3-vl-embedding", {"api_key": "test-key"}, [document]
        )


def test_multimodal_rejects_invalid_image_before_http(wire):
    _, calls, _ = wire
    document = MultiModalContent(content_type=MultiModalContentType.IMAGE, content="not base64")
    with pytest.raises(InvokeBadRequestError):
        embedding("qwen3-vl-embedding").invoke_multimodal(
            "qwen3-vl-embedding", {"api_key": "test-key"}, [document]
        )
    assert calls == []
