import base64
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
import yaml
from dify_plugin.entities.model import AIModelEntity, EmbeddingInputType
from dify_plugin.entities.model.message import (
    DocumentPromptMessageContent,
    TextPromptMessageContent,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeBadRequestError

from models.llm.llm import TokenerLargeLanguageModel
from models.text_embedding.text_embedding import TokenerTextEmbeddingModel
from scripts.sync_catalog import render_catalog


def schema(kind, model):
    return AIModelEntity.model_validate(
        yaml.safe_load(Path(f"models/{kind}/{model}.yaml").read_text())
    )


def response(body):
    result = requests.Response()
    result.status_code = 200
    result._content = json.dumps(body).encode()
    return result


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("attachment", ["url", "base64_data"])
def test_qwen_long_rejects_document_before_sending_text_only(stream, attachment):
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
    with patch("requests.post") as post, pytest.raises(InvokeBadRequestError):
        list(model.invoke("qwen-long", {"api_key": "test"}, messages, {}, stream=stream))
    post.assert_not_called()
    assert messages[0].content[1] is document


@pytest.mark.parametrize("model_id", ["gpt-4o-mini", "gpt-4o-mini-2024-07-18"])
@pytest.mark.parametrize(
    "parameters",
    [
        {"temperature": 0.2, "top_p": 0.3, "max_tokens": 1500},
        {"temperature": 0, "top_p": 0, "presence_penalty": -2, "frequency_penalty": 2},
        {"temperature": 2, "top_p": 1, "presence_penalty": 0.2, "frequency_penalty": -0.4},
    ],
)
def test_gpt_4o_mini_public_invoke_preserves_supported_parameters(model_id, parameters):
    model = TokenerLargeLanguageModel(model_schemas=[schema("llm", model_id)])
    with patch(
        "requests.post",
        return_value=response(
            {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }
        ),
    ) as post:
        list(
            model.invoke(
                model_id,
                {"api_key": "test"},
                [UserPromptMessage(content="Hi")],
                parameters,
                stream=False,
            )
        )
    kwargs = post.call_args.kwargs
    body = kwargs.get("json") or json.loads(kwargs["data"])
    assert {key: body.get(key) for key in parameters} == parameters


@pytest.mark.parametrize(
    "input_type,task_type",
    [
        (EmbeddingInputType.QUERY, "RETRIEVAL_QUERY"),
        (EmbeddingInputType.DOCUMENT, "RETRIEVAL_DOCUMENT"),
    ],
)
def test_embedding_001_public_invoke_preserves_retrieval_purpose(input_type, task_type):
    model_id = "gemini-embedding-001"
    model = TokenerTextEmbeddingModel(model_schemas=[schema("text_embedding", model_id)])
    with patch(
        "requests.post",
        return_value=response(
            {
                "data": [{"index": 0, "embedding": [0.1, 0.2]}],
                "usage": {"total_tokens": 777},
            }
        ),
    ) as post:
        result = model.invoke(
            model_id, {"api_key": "test"}, ["same text"], input_type=input_type
        )
    body = post.call_args.kwargs["json"]
    assert body["input"] == ["same text"]
    assert body["task_type"] == task_type
    assert result.usage.tokens == 777


@pytest.mark.parametrize(
    "input_type,prefix",
    [
        (EmbeddingInputType.QUERY, "task: search result | query: "),
        (EmbeddingInputType.DOCUMENT, "title: none | text: "),
    ],
)
def test_embedding_2_public_invoke_preserves_retrieval_purpose(input_type, prefix):
    model_id = "gemini-embedding-2-preview"
    model = TokenerTextEmbeddingModel(model_schemas=[schema("text_embedding", model_id)])
    with patch(
        "requests.post",
        return_value=response(
            {
                "data": [{"index": 0, "embedding": [0.1, 0.2]}],
                "usage": {"total_tokens": 1},
            }
        ),
    ) as post:
        model.invoke(model_id, {"api_key": "test"}, ["same text"], input_type=input_type)
    body = post.call_args.kwargs["json"]
    assert body["input"] == [prefix + "same text"]
    assert "task_type" not in body


def test_catalog_sync_retains_gpt_4o_mini_parameter_contract():
    model = {
        "id": "gpt-4o-mini",
        "label": "gpt-4o-mini",
        "provider": "openai",
        "modelType": "llm",
        "mode": "chat",
        "contextSize": 128000,
        "maxOutputTokens": 16384,
        "capabilities": ["streaming"],
        "pricing": {
            "currency": "USD",
            "inputPerMillion": "0.15",
            "outputPerMillion": "0.6",
            "cacheReadPerMillion": None,
        },
        "deprecated": False,
    }
    files = render_catalog(
        {"schemaVersion": 1, "catalogRevision": f"sha256:{'a' * 64}", "models": [model]}
    )
    generated = AIModelEntity.model_validate(yaml.safe_load(files["gpt-4o-mini.yaml"]))
    rules = {rule.name: rule for rule in generated.parameter_rules}
    assert {"temperature", "top_p", "presence_penalty", "frequency_penalty"} <= rules.keys()
    assert rules["top_p"].min == 0


def test_catalog_sync_keeps_qwen_long_document_rejection_reachable():
    model = {
        "id": "qwen-long",
        "label": "qwen-long",
        "provider": "qwen",
        "modelType": "llm",
        "mode": "chat",
        "contextSize": 10000000,
        "maxOutputTokens": 32768,
        "capabilities": ["streaming", "structured_output"],
        "pricing": {
            "currency": "USD",
            "inputPerMillion": "0.072000",
            "outputPerMillion": "0.287000",
            "cacheReadPerMillion": None,
        },
        "deprecated": False,
    }
    files = render_catalog(
        {"schemaVersion": 1, "catalogRevision": f"sha256:{'a' * 64}", "models": [model]}
    )
    generated = yaml.safe_load(files["qwen-long.yaml"])
    assert "document" in generated["features"]
    assert files["qwen-long.yaml"] == Path("models/llm/qwen-long.yaml").read_text()
