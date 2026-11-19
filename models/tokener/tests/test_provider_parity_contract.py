import json

import pytest
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeBadRequestError
from protocol_http import CREDENTIALS, SCHEMA, TOOL, chat_result, contents, invoke
from protocol_http import llm as llm
from protocol_http import registry as registry
from protocol_http import wire as wire
from test_anthropic_protocol import claude_result
from test_gemini_protocol import gemini_result


@pytest.mark.parametrize("model", ["qwen-plus", "deepseek-v4-pro", "grok-4.5"])
def test_chat_identity_matches_source_provider(llm, wire, model):
    _, requests, replies = wire
    replies.append((200, {}, chat_result()))
    chunks = list(
        llm.invoke(
            model,
            CREDENTIALS,
            [UserPromptMessage(content="hello")],
            {"enable_thinking": False},
            stream=False,
            user="end-user-uuid-123",
        )
    )
    assert contents(chunks) == "ok"
    assert "user" not in requests[0][2]
    assert "end-user-uuid-123" not in json.dumps(requests[0][2])


@pytest.mark.parametrize(
    "mode,schema", [("JSON", None), ("JSON", "  "), ("XML", json.dumps(SCHEMA))]
)
def test_anthropic_template_preserves_source_request_and_output(llm, wire, mode, schema):
    _, requests, replies = wire
    fenced = f"```{mode}\nanswer\n```"
    replies.append((200, {}, claude_result(content=[{"type": "text", "text": fenced}])))
    parameters = {"response_format": mode}
    if schema is not None:
        parameters["json_schema"] = schema
    chunks = invoke(llm, "claude-sonnet-5", parameters)
    body = requests[0][2]
    assert "<instructions>" in str(body["system"])
    assert "format" not in body.get("output_config", {})
    assert body["messages"][-1] == {"role": "user", "content": [{"type": "text", "text": "hello"}]}
    assert contents(chunks) == fenced


@pytest.mark.parametrize(
    "schema",
    [
        SCHEMA,
        {"schema": SCHEMA, "name": "llm_response"},
        {"schema": {"type": "string"}, "name": "custom"},
    ],
)
def test_anthropic_schema_preserves_source_envelope_contract(llm, wire, schema):
    _, requests, replies = wire
    replies.append((200, {}, claude_result()))
    invoke(llm, "claude-sonnet-5", {"response_format": "JSON", "json_schema": json.dumps(schema)})
    expected = schema["schema"] if schema.get("name") == "llm_response" else schema
    assert requests[0][2]["output_config"]["format"]["schema"] == expected


@pytest.mark.parametrize("mode", ["JSON", "json", "XML"])
@pytest.mark.parametrize("model", ["claude-sonnet-4-6", "gemini-3.1-flash-lite"])
def test_sdk_response_format_reaches_native_protocol(llm, wire, model, mode):
    _, requests, replies = wire
    reply = claude_result() if model.startswith("claude") else gemini_result([{"text": "ok"}])
    replies.append((200, {}, reply))
    invoke(llm, model, {"response_format": mode})
    body = requests[0][2]
    if mode == "XML":
        assert ("<instructions>" in str(body)) == model.startswith("claude")
    elif model.startswith("gemini"):
        assert body["generationConfig"]["responseMimeType"] == "application/json"
    else:
        assert any("JSON object" in part["text"] for part in body["system"])


def test_gemini_xml_does_not_override_source_native_schema(llm, wire):
    _, requests, replies = wire
    fenced = "```JSON\n{}\n```"
    replies.append((200, {}, gemini_result([{"text": fenced}])))
    chunks = invoke(
        llm, "gemini-2.5-pro", {"response_format": "XML", "json_schema": json.dumps(SCHEMA)}
    )
    body = requests[0][2]
    assert body["generationConfig"]["responseJsonSchema"] == SCHEMA
    assert "<instructions>" not in str(body)
    assert contents(chunks) == fenced


def test_gemini_native_constraints_and_code_blocks(llm, wire):
    _, requests, replies = wire
    result = gemini_result(
        [
            {"executableCode": {"language": "PYTHON", "code": "print(4)"}},
            {"codeExecutionResult": {"outcome": "OUTCOME_OK", "output": "4"}},
        ]
    )
    result["candidates"][0]["groundingMetadata"] = {
        "groundingChunks": [{"web": {"uri": "https://example.com", "title": "Source"}}]
    }
    replies.append((200, {}, result))
    chunks = invoke(
        llm,
        "gemini-3.8-flash",
        {
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 5,
            "grounding": True,
            "url_context": True,
            "code_execution": True,
            "service_tier": "standard",
        },
        tools=[TOOL],
    )
    body = requests[0][2]
    assert body["serviceTier"] == "standard"
    assert not {"temperature", "topP", "topK"} & body.get("generationConfig", {}).keys()
    assert len(body["tools"]) == 1 and "functionDeclarations" in body["tools"][0]
    assert "```python\nprint(4)\n```" in contents(chunks)
    assert "```\n4\n```" in contents(chunks)


def test_gemini_auto_image_and_json_schema_do_not_emit_ui_defaults_or_sources(llm, wire):
    _, requests, replies = wire
    replies.extend([(200, {}, gemini_result([{"text": "ok"}]))] * 2)
    invoke(llm, "gemini-3-pro-image-preview", {"aspect_ratio": "Auto", "resolution": "1K"})
    invoke(llm, "gemini-3.1-flash-lite", {"response_format": "JSON", "json_schema": SCHEMA})
    assert requests[0][2]["generationConfig"]["imageConfig"] == {"imageSize": "1K"}
    assert requests[1][2]["generationConfig"]["responseJsonSchema"] == SCHEMA


@pytest.mark.parametrize("ttl,expected", [("5m", 2350), ("1h", 3100)])
def test_anthropic_cache_usage_and_adaptive_version(llm, wire, ttl, expected):
    _, requests, replies = wire
    replies.append(
        (
            200,
            {},
            claude_result(
                usage={
                    "input_tokens": 100,
                    "cache_creation_input_tokens": 1000,
                    "cache_read_input_tokens": 10000,
                    "output_tokens": 2,
                }
            ),
        )
    )
    chunks = invoke(llm, "claude-opus-4-7", {"prompt_caching_ttl": ttl, "thinking": True})
    assert requests[0][1]["anthropic-version"] == "2026-10-21"
    assert chunks[-1].delta.usage.prompt_tokens == expected


def test_openai_long_embedding_is_split_weighted_and_normalized(registry, wire):
    _, requests, replies = wire
    replies.append(
        (
            200,
            {},
            {
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ],
                "usage": {"total_tokens": 9001},
            },
        )
    )
    embedding = registry.get_model_instance("tokener", ModelType.TEXT_EMBEDDING)
    result = embedding.invoke("text-embedding-3-small", CREDENTIALS, ["hello " * 9000])
    batch = requests[0][2]["input"]
    assert all(isinstance(chunk, list) and len(chunk) <= 8191 for chunk in batch)
    assert sum(map(len, batch)) == 9001
    norm = (8191**2 + 810**2) ** 0.5
    assert result.embeddings[0] == pytest.approx([8191 / norm, 810 / norm])
    assert result.usage.tokens == 9001


def test_source_required_defaults_reach_each_protocol(llm, wire):
    _, requests, replies = wire
    replies.extend(
        [
            (200, {}, claude_result()),
            (200, {}, gemini_result([{"text": "ok"}])),
            (200, {}, chat_result()),
        ]
    )
    invoke(llm, "claude-sonnet-5")
    invoke(llm, "gemini-3.1-pro-preview")
    invoke(llm, "qwen-mt-plus")
    claude, gemini, tongyi = [request[2] for request in requests]
    assert claude["max_tokens"] == 128000
    assert claude["thinking"]["type"] == "adaptive"
    assert claude["output_config"]["effort"] == "high"
    assert gemini["generationConfig"]["maxOutputTokens"] == 65536
    assert gemini["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "HIGH"
    assert tongyi["translation_options"] == {
        "source_lang": "auto",
        "target_lang": "Chinese",
        "domains": None,
    }


def test_tongyi_hosted_models_preserve_controls_and_force_stream(llm, wire):
    _, requests, replies = wire
    for model in ("kimi-k2.5", "glm-5", "deepseek-v4-pro"):
        replies.append((200, {}, b"data: " + json.dumps(chat_result()).encode() + b"\n\n"))
        invoke(llm, model, {"enable_thinking": True}, stream=False)
    for _, _, body in requests:
        assert body["enable_thinking"] is True
        assert body["stream"] is True
        assert body["incremental_output"] is True


@pytest.mark.parametrize(
    "model,alias",
    [
        ("claude-sonnet-5", "max_tokens_to_sample"),
        ("gemini-3.1-pro-preview", "max_tokens"),
        ("gpt-5.4-nano", "max_output_tokens"),
    ],
)
def test_explicit_token_alias_is_not_replaced_by_required_default(llm, wire, model, alias):
    _, requests, replies = wire
    result = claude_result() if model.startswith("claude") else gemini_result([{"text": "ok"}])
    if model.startswith("gpt"):
        result = {
            "status": "completed",
            "output": [],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    replies.append((200, {}, result))
    invoke(llm, model, {alias: 123})
    body = requests[0][2]
    actual = (
        body["generationConfig"]["maxOutputTokens"]
        if model.startswith("gemini")
        else body.get("max_output_tokens", body.get("max_tokens"))
    )
    assert actual == 123


@pytest.mark.parametrize(
    "model,alias",
    [
        ("claude-sonnet-5", "max_tokens_to_sample"),
        ("gemini-3.1-pro-preview", "max_tokens"),
        ("gpt-5.4-nano", "max_output_tokens"),
    ],
)
def test_token_alias_keeps_source_limit_validation(llm, wire, model, alias):
    _, requests, _ = wire
    with pytest.raises((ValueError, InvokeBadRequestError)):
        invoke(llm, model, {alias: 10**10})
    assert not requests


def test_gemini_long_embedding_counts_splits_and_merges(registry, wire, monkeypatch):
    _, requests, replies = wire
    embedding = registry.get_model_instance("tokener", ModelType.TEXT_EMBEDDING)
    monkeypatch.setattr(type(embedding), "_get_context_size", lambda *args: 4)
    replies.extend(
        [
            (200, {}, {"totalTokens": 5}),
            (200, {}, {"totalTokens": 3}),
            (200, {}, {"totalTokens": 2}),
            (
                200,
                {},
                {
                    "embeddings": [
                        {"values": [1.0, 0.0], "statistics": {"tokenCount": 3}},
                        {"values": [0.0, 1.0], "statistics": {"tokenCount": 2}},
                    ]
                },
            ),
        ]
    )
    result = embedding.invoke("gemini-embedding-001", CREDENTIALS, ["abcde"])
    assert [request[0] for request in requests] == [
        "/v1beta/models/gemini-embedding-001:countTokens",
    ] * 3 + ["/v1beta/models/gemini-embedding-001:batchEmbedContents"]
    batch = requests[-1][2]["requests"]
    assert [item["content"]["parts"][0]["text"] for item in batch] == ["abcd", "e"]
    assert {item["taskType"] for item in batch} == {"RETRIEVAL_DOCUMENT"}
    assert result.embeddings[0] == pytest.approx([3 / 13**0.5, 2 / 13**0.5])
    assert result.usage.tokens == 5


def test_tongyi_embedding_truncates_before_transport(registry, wire, monkeypatch):
    _, requests, replies = wire
    embedding = registry.get_model_instance("tokener", ModelType.TEXT_EMBEDDING)
    monkeypatch.setattr(type(embedding), "_get_context_size", lambda *args: 4)
    monkeypatch.setattr(type(embedding), "_get_num_tokens_by_gpt2", lambda *args: 10)
    replies.append(
        (200, {}, {"data": [{"index": 0, "embedding": [1, 2]}], "usage": {"total_tokens": 4}})
    )
    embedding.invoke("text-embedding-v4", CREDENTIALS, ["abcdefghij"])
    assert requests[0][2]["input"] == ["abcd"]


def test_anthropic_select_tool_preserves_source_schema_without_mutation(llm, wire):
    _, requests, replies = wire
    replies.append((200, {}, claude_result()))
    tool = PromptMessageTool(
        name="pick",
        description="Choose",
        parameters={
            "type": "object",
            "properties": {
                "choice": {"type": "select", "options": [{"value": "a"}, {"value": "b"}]}
            },
        },
    )
    invoke(llm, "claude-sonnet-4-6", tools=[tool])
    prop = requests[0][2]["tools"][0]["input_schema"]["properties"]["choice"]
    assert prop["type"] == "string" and prop["enum"] == ["a", "b"]
    assert tool.parameters["properties"]["choice"]["type"] == "select"


def test_gemini_latest_scalar_system_and_structured_promotion(llm, wire):
    _, requests, replies = wire
    replies.extend([(200, {}, gemini_result([{"text": "ok"}]))] * 2)
    invoke(
        llm,
        "gemini-3.1-flash-lite",
        messages=[
            SystemPromptMessage(content="old"),
            SystemPromptMessage(content="new"),
            UserPromptMessage(content="hello"),
        ],
    )
    invoke(
        llm,
        "gemini-3.1-flash-lite",
        messages=[
            SystemPromptMessage(content=[TextPromptMessageContent(data="structured")]),
            UserPromptMessage(content="hello"),
        ],
    )
    assert requests[0][2]["systemInstruction"]["parts"] == [{"text": "new"}]
    assert requests[1][2]["systemInstruction"]["parts"] == [{"text": "structured"}]
    assert requests[1][2]["contents"] == [{"role": "user", "parts": [{"text": "hello"}]}]


def test_gemini_disallowed_budget_and_assistant_prefill(llm, wire):
    _, requests, replies = wire
    replies.append((200, {}, gemini_result([{"text": "ok"}])))
    invoke(llm, "gemini-3.8-flash", {"thinking_mode": True, "thinking_budget": 100})
    assert "thinkingBudget" not in requests[0][2]["generationConfig"].get("thinkingConfig", {})
    with pytest.raises(InvokeBadRequestError):
        invoke(
            llm,
            "gemini-3.8-flash",
            messages=[UserPromptMessage(content="hello"), AssistantPromptMessage(content="prefix")],
        )
    assert len(requests) == 1
