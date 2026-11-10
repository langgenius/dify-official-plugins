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
from scripts.sync_catalog import render_catalog


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
@pytest.mark.parametrize("attachment", ["url", "base64_data"])
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
    with (
        patch.object(
            model, "_transform_invoke_error", wraps=model._transform_invoke_error
        ) as transform,
        pytest.raises(InvokeBadRequestError) as rejected,
    ):
        list(model.invoke("qwen-long", {"api_key": "test"}, messages, {}, stream=stream))
    upstream.assert_not_called()
    assert rejected.value is transform.call_args.args[0]
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
def test_gpt_4o_mini_public_invoke_preserves_supported_parameters(model_id, parameters, upstream):
    model = TokenerLargeLanguageModel(model_schemas=[schema("llm", model_id)])
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
    assert {key: body.get(key) for key in parameters} == parameters


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
    response_body = json.loads(upstream.return_value.content)
    response_body["usage"]["total_tokens"] = 777
    upstream.return_value._content = json.dumps(response_body).encode()
    result = model.invoke(model_id, {"api_key": "test"}, ["same text"], input_type=input_type)
    body = upstream.call_args.kwargs["json"]
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
def test_embedding_2_public_invoke_preserves_retrieval_purpose(input_type, prefix, upstream):
    model_id = "gemini-embedding-2-preview"
    model = TokenerTextEmbeddingModel(model_schemas=[schema("text_embedding", model_id)])
    model.invoke(model_id, {"api_key": "test"}, ["same text"], input_type=input_type)
    body = upstream.call_args.kwargs["json"]
    assert body["input"] == [prefix + "same text"]
    assert "task_type" not in body


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
        "maxOutputTokens": definition["parameter_rules"][0]["max"],
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
    generated = AIModelEntity.model_validate(yaml.safe_load(files[f"{model_id}.yaml"]))
    if model_id == "qwen-long":
        assert ModelFeature.DOCUMENT in generated.features
        assert files[f"{model_id}.yaml"] == path.read_text()
    else:
        rules = {rule.name: rule for rule in generated.parameter_rules}
        assert {"temperature", "top_p", "presence_penalty", "frequency_penalty"} <= rules.keys()
        assert rules["top_p"].min == 0
