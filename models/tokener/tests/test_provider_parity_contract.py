import json

import pytest
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.message import (
    PromptMessageTool,
    UserPromptMessage,
)
from protocol_http import (
    CREDENTIALS,
    SCHEMA,
    TOOL,
    chat_result,
    contents,
    invoke,
)
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
    assert "end-user-uuid-123" not in json.dumps(requests[0][2])


def test_anthropic_schema_preserves_source_envelope_contract(llm, wire):
    schema = SCHEMA
    _, requests, replies = wire
    replies.append((200, {}, claude_result()))
    invoke(llm, "claude-sonnet-5", {"response_format": "JSON", "json_schema": json.dumps(schema)})
    assert requests[0][2]["output_config"]["format"]["schema"] == SCHEMA


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
    result = embedding.invoke("text-embedding-3-small", CREDENTIALS, ["hello " * 9000], user="user")
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
    }


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
