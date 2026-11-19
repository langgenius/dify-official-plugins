import base64
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
import yaml
from dify_plugin.entities.model import (
    AIModelEntity,
    EmbeddingInputType,
    ModelFeature,
)
from dify_plugin.entities.model.message import (
    DocumentPromptMessageContent,
    TextPromptMessageContent,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeBadRequestError

from models.llm.llm import TokenerLargeLanguageModel
from models.text_embedding.text_embedding import TokenerTextEmbeddingModel
from scripts.source_contracts import apply_source_contracts, load_source_contracts
from scripts.sync_catalog import SOURCE_ROOT, render_catalog


def schema(kind, model):
    return AIModelEntity.model_validate(
        yaml.safe_load(Path(f"models/{kind}/{model}.yaml").read_text())
    )


@pytest.fixture
def upstream():
    result = requests.Response()
    result.status_code = 200
    result._content = json.dumps(
        {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "data": [{"index": 0, "embedding": [0.1, 0.2]}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 1},
        }
    ).encode()
    with patch("requests.post", return_value=result) as post:
        yield post


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("attachment", ["url"])
def test_qwen_long_rejects_document_before_sending_text_only(stream, attachment, upstream):
    model = TokenerLargeLanguageModel(model_schemas=[schema("llm", "qwen-long")])
    document = DocumentPromptMessageContent(
        format="pdf",
        mime_type="application/pdf",
        **{
            attachment: (
                "https://example.invalid/document.pdf"
                if attachment == "url"
                else base64.b64encode(b"%PDF-1.7 unique document fact").decode()
            )
        },
    )
    messages = [UserPromptMessage(content=[TextPromptMessageContent(data="Summarize"), document])]
    with pytest.raises(InvokeBadRequestError):
        list(model.invoke("qwen-long", {"api_key": "test"}, messages, {}, stream=stream))
    upstream.assert_not_called()
    assert messages[0].content[1] is document


@pytest.mark.parametrize("model_id", ["gpt-4o-mini", "gpt-4o-mini-2024-07-18"])
@pytest.mark.parametrize(
    "parameters",
    [
        {"temperature": 0.2, "top_p": 0.3, "max_tokens": 1500},
        {"temperature": 0, "top_p": 0, "presence_penalty": 0, "frequency_penalty": 1},
        {"temperature": 1, "top_p": 1, "presence_penalty": 0.2, "frequency_penalty": 0.4},
    ],
)
def test_gpt_4o_mini_public_invoke_follows_source_responses_contract(
    model_id, parameters, upstream
):
    model = TokenerLargeLanguageModel(model_schemas=[schema("llm", model_id)])
    if any(parameters.get(name, 0) != 0 for name in ("presence_penalty", "frequency_penalty")):
        with pytest.raises(InvokeBadRequestError):
            list(
                model.invoke(
                    model_id,
                    {"api_key": "test"},
                    [UserPromptMessage(content="Hi")],
                    parameters,
                    stream=False,
                )
            )
        upstream.assert_not_called()
        return
    upstream.return_value._content = json.dumps(
        {
            "status": "completed",
            "output_text": "ok",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    ).encode()
    list(
        model.invoke(
            model_id,
            {"api_key": "test"},
            [UserPromptMessage(content="Hi")],
            parameters,
            stream=False,
        )
    )
    kwargs = upstream.call_args.kwargs
    body = kwargs.get("json") or json.loads(kwargs["data"])
    expected = {
        ("max_output_tokens" if key == "max_tokens" else key): value
        for key, value in parameters.items()
    }
    assert {key: body.get(key) for key in expected} == expected


@pytest.mark.parametrize(
    "input_type,task_type",
    [
        (EmbeddingInputType.QUERY, "RETRIEVAL_QUERY"),
        (EmbeddingInputType.DOCUMENT, "RETRIEVAL_DOCUMENT"),
    ],
)
def test_embedding_001_public_invoke_preserves_retrieval_purpose(input_type, task_type, upstream):
    model_id = "gemini-embedding-001"
    model = TokenerTextEmbeddingModel(model_schemas=[schema("text_embedding", model_id)])
    replies = []
    for body in (
        {"totalTokens": 777},
        {"embeddings": [{"values": [0.1, 0.2], "statistics": {"tokenCount": 777}}]},
    ):
        reply = requests.Response()
        reply.status_code = 200
        reply._content = json.dumps(body).encode()
        replies.append(reply)
    upstream.side_effect = replies
    result = model.invoke(model_id, {"api_key": "test"}, ["same text"], input_type=input_type)
    body = upstream.call_args.kwargs["json"]["requests"][0]
    assert body["content"]["parts"] == [{"text": "same text"}]
    assert body["taskType"] == task_type
    assert result.usage.tokens == 777


@pytest.mark.parametrize(
    "input_type,prefix",
    [
        (EmbeddingInputType.QUERY, "task: search result | query: "),
        (EmbeddingInputType.DOCUMENT, "title: none | text: "),
    ],
)
def test_embedding_2_public_invoke_preserves_retrieval_purpose(input_type, prefix, upstream):
    model_id = "gemini-embedding-2-preview"
    model = TokenerTextEmbeddingModel(model_schemas=[schema("text_embedding", model_id)])
    model.invoke(model_id, {"api_key": "test"}, ["same text"], input_type=input_type)
    body = upstream.call_args.kwargs["json"]
    assert body["input"] == [prefix + "same text"]
    assert "task_type" not in body


@pytest.mark.parametrize("model_id", ["embed-english-v3", "embed-multilingual-v3", "embed-v4"])
@pytest.mark.parametrize(
    "input_type,upstream_type",
    [
        (EmbeddingInputType.QUERY, "search_query"),
        (EmbeddingInputType.DOCUMENT, "search_document"),
    ],
)
def test_cohere_public_invoke_preserves_retrieval_purpose(
    model_id, input_type, upstream_type, upstream
):
    model = TokenerTextEmbeddingModel(model_schemas=[schema("text_embedding", model_id)])
    model.invoke(model_id, {"api_key": "test"}, ["same text"], input_type=input_type)
    body = upstream.call_args.kwargs["json"]
    assert body["input"] == ["same text"]
    assert body["input_type"] == upstream_type


@pytest.mark.parametrize("model_id", ["gpt-4o-mini", "qwen-long"])
def test_catalog_sync_retains_semantic_contracts(model_id):
    path = Path(f"models/llm/{model_id}.yaml")
    definition = yaml.safe_load(path.read_text())
    model = {
        "id": model_id,
        "label": model_id,
        "provider": "qwen" if model_id == "qwen-long" else "openai",
        "modelType": "llm",
        "mode": "chat",
        "contextSize": definition["model_properties"]["context_size"],
        "maxOutputTokens": next(
            rule["max"] for rule in definition["parameter_rules"] if rule["name"] == "max_tokens"
        )
        or definition["model_properties"]["context_size"],
        "capabilities": ["streaming"] + (["structured_output"] if model_id == "qwen-long" else []),
        "deprecated": False,
        "pricing": {
            "currency": "USD",
            "inputPerMillion": definition["pricing"]["input"],
            "outputPerMillion": definition["pricing"]["output"],
            "cacheReadPerMillion": None,
        },
    }
    files = render_catalog(
        {"schemaVersion": 1, "catalogRevision": f"sha256:{'a' * 64}", "models": [model]}
    )
    apply_source_contracts(files, load_source_contracts(SOURCE_ROOT))
    generated = AIModelEntity.model_validate(yaml.safe_load(files[f"{model_id}.yaml"]))
    if model_id == "qwen-long":
        assert ModelFeature.DOCUMENT in generated.features
        assert files[f"{model_id}.yaml"] == path.read_text()
    else:
        rules = {rule.name: rule for rule in generated.parameter_rules}
        assert {"temperature", "top_p", "presence_penalty", "frequency_penalty"} <= rules.keys()
        assert rules["top_p"].min == 0
