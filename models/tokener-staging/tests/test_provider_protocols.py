import io
import json
import wave

import pytest
from dify_plugin.entities.model import EmbeddingInputType, ModelType
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    SystemPromptMessage,
    UserPromptMessage,
)
from dify_plugin.entities.model.text_embedding import MultiModalContent
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from protocol_http import CREDENTIALS, IMAGE, SCHEMA, USER, chat_result, contents, invoke, sse
from protocol_http import llm as llm
from protocol_http import registry as registry
from protocol_http import wire as wire


def test_tongyi_chat_sse_strips_history_and_preserves_search_reasoning_and_media_schema(llm, wire):
    _, requests, replies = wire
    replies.append(
        (
            200,
            {},
            sse(
                "data",
                choices=[
                    {"index": 0, "delta": {"reasoning_content": "analysis"}, "finish_reason": None}
                ],
            )
            + sse(
                "data",
                choices=[
                    {"index": 0, "delta": {"content": '{"answer":4}'}, "finish_reason": "stop"}
                ],
            )
            + sse("data", choices=[], usage={"prompt_tokens": 3, "completion_tokens": 4})
            + b"data: [DONE]\r\n\r\n",
        )
    )
    chunks = invoke(
        llm,
        "qwen3.8-max",
        {
            "enable_search": True,
            "enable_thinking": True,
            "thinking_budget": 1024,
            "reasoning_effort": "low",
            "temperature": 0.2,
            "top_p": 0.4,
            "top_k": 20,
            "repetition_penalty": 1.1,
            "seed": 42,
            "response_format": "json_schema",
            "json_schema": SCHEMA,
        },
        messages=[
            AssistantPromptMessage(content="<think>\nprivate reasoning\n</think>old"),
            UserPromptMessage(content=[IMAGE]),
        ],
    )
    assert "analysis" in contents(chunks) and '{"answer":4}' in contents(chunks)
    path, _, body = requests[0]
    assert path == "/v1/chat/completions"
    assert body["messages"][1]["content"] == "old"
    assert json.dumps(SCHEMA) in body["messages"][0]["content"]
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0.6
    assert body["top_k"] == 20 and body["top_p"] == 0.4 and body["seed"] == 42
    assert body["repetition_penalty"] == 1.1
    assert body["enable_search"] is True and body["stream"] is True
    assert body["enable_thinking"] is True and body["thinking_budget"] == 1024
    assert body["reasoning_effort"] == "low"


def test_tongyi_translation_and_nonstream_thinking(llm, wire):
    _, requests, replies = wire
    replies.extend([(200, {}, chat_result("你好")), (200, {}, chat_result("ok", "reason"))])
    invoke(
        llm,
        "qwen-mt-plus",
        {"source_lang": "English", "target_lang": "Chinese", "domains": "finance"},
        stream=True,
        messages=[SystemPromptMessage(content="omit"), USER],
    )
    assert requests[0][2]["translation_options"] == {
        "source_lang": "English",
        "target_lang": "Chinese",
        "domains": "finance",
    }
    assert requests[0][2]["messages"] == [{"role": "user", "content": "hello"}]
    assert requests[0][2]["stream"] is False
    chunks = invoke(llm, "qwen3-vl-plus", {"enable_thinking": False, "thinking_budget": 16})
    assert requests[1][2]["thinking_budget"] == 16
    assert contents(chunks) == "<think>\nreason\n</think>\nok"


def test_xai_only_strips_penalties_and_stop_from_reasoning_models(llm, wire):
    _, requests, replies = wire
    replies.extend([(200, {}, chat_result("ok", "reason")), (200, {}, chat_result())])
    params = {
        "search_parameters": '{"mode":"auto"}',
        "reasoning_effort": "low",
        "temperature": 0.7,
        "top_p": 0.6,
        "presence_penalty": 1,
        "frequency_penalty": 1,
    }
    chunks = invoke(llm, "grok-4.20-0309-reasoning", params, stop=["end"])
    invoke(llm, "grok-4.20-0309-non-reasoning", params, stop=["end"])
    assert contents(chunks) == "<think>\nreason\n</think>\nok"
    for request in requests:
        assert request[0] == "/v1/chat/completions"
        assert request[2]["search_parameters"] == {"mode": "auto"}
        assert request[2]["reasoning_effort"] == "low"
        assert request[2]["temperature"] == 0.7 and request[2]["top_p"] == 0.6
    removed = {"stop", "presence_penalty", "frequency_penalty"}
    assert not (removed & requests[0][2].keys())
    assert removed <= requests[1][2].keys()


@pytest.mark.parametrize(
    "value", ["{", "[]", "null", '{"value":NaN}', '{"sources":[{"api_key":"injected"}]}']
)
def test_xai_invalid_or_transport_search_parameters_never_send(llm, wire, value):
    _, requests, _ = wire
    with pytest.raises(InvokeBadRequestError):
        invoke(llm, "grok-4.3", {"search_parameters": value})
    assert requests == []


@pytest.mark.parametrize(
    "field", ["openai_api_base", "ANTHROPIC_API_KEY", "baseURL", "route", "x-Goog-API-Key"]
)
def test_native_adapters_reject_transport_parameters_before_send(llm, wire, field):
    _, requests, _ = wire
    with pytest.raises(InvokeBadRequestError):
        invoke(llm, "gpt-6-luna", {field: "ignored"})
    assert requests == []


@pytest.mark.parametrize(
    "status,error",
    [
        (301, InvokeServerUnavailableError),
        (400, InvokeBadRequestError),
        (403, InvokeAuthorizationError),
        (429, InvokeRateLimitError),
        (502, InvokeServerUnavailableError),
    ],
)
def test_native_http_errors_and_redirects_are_not_hidden_by_chat_fallback(llm, wire, status, error):
    _, requests, replies = wire
    replies.append((status, {"Location": "https://untrusted.invalid"}, {"private": "error detail"}))
    with pytest.raises(error) as caught:
        invoke(llm, "gemini-3-flash-preview")
    assert "error detail" not in str(caught.value)
    assert [r[0] for r in requests] == ["/v1beta/models/gemini-3-flash-preview:generateContent"]


def wav(frames, *, rate=24000):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as audio:
        audio.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        audio.writeframes(frames)
    return stream.getvalue()


@pytest.mark.parametrize("valid", [True, False])
def test_speech_qwen_merges_pcm_and_rejects_mismatched_segments(registry, wire, valid):
    _, requests, replies = wire
    first, second = b"\x01\x00", b"\x02\x00"
    replies.extend([(200, {}, wav(first)), (200, {}, wav(second, rate=24000 if valid else 22050))])
    model = registry.get_model_instance("tokener", ModelType.TTS)
    chunks = model.invoke("qwen3-tts-flash", "", CREDENTIALS, "x" * 513, "")
    if valid:
        with wave.open(io.BytesIO(b"".join(chunks)), "rb") as audio:
            assert audio.getframerate() == 24000
            assert audio.getnframes() == 2
            assert audio.readframes(2) == first + second
    else:
        with pytest.raises(InvokeServerUnavailableError, match="invalid WAV"):
            next(chunks)
    assert [r[0] for r in requests] == ["/v1/audio/speech"] * 2
    assert [len(r[2]["input"]) for r in requests] == [512, 1]
    assert all((r[2]["voice"], r[2]["response_format"]) == ("Cherry", "wav") for r in requests)


def test_dated_openai_tts_is_discoverable_with_alloy(registry, wire):
    _, requests, replies = wire
    replies.append((200, {}, b"audio"))
    model = registry.get_model_instance("tokener", ModelType.TTS)
    name = "gpt-4o-mini-tts-2025-12-15"
    assert b"".join(model.invoke(name, "", CREDENTIALS, "hello", "")) == b"audio"
    assert requests[0][2] == {
        "model": name,
        "voice": "alloy",
        "input": "hello",
        "response_format": "mp3",
    }


def test_embedding_null_index_and_native_multimodal_keep_distinct_paths(registry, wire):
    _, requests, replies = wire
    old = {"data": [{"index": None, "embedding": [1, 2]}], "usage": {"total_tokens": 7}}
    replies.extend(
        [
            (200, {}, old),
            (200, {}, old),
            (
                200,
                {},
                {
                    "embeddings": [
                        {"values": [1, 2], "statistics": {"tokenCount": 4}},
                        {"values": [2, 3], "statistics": {"tokenCount": 5}},
                    ]
                },
            ),
        ]
    )
    model = registry.get_model_instance("tokener", ModelType.TEXT_EMBEDDING)
    name = "gemini-embedding-2-preview"
    text = MultiModalContent(content_type="text", content="anchor")
    image = MultiModalContent(content_type="image", content=IMAGE.base64_data)
    query = model.invoke(name, CREDENTIALS, ["anchor"], input_type=EmbeddingInputType.QUERY)
    plain = model.invoke_multimodal(name, CREDENTIALS, [text])
    mixed = model.invoke_multimodal(name, CREDENTIALS, [text, image])
    assert query.embeddings == plain.embeddings == [[1, 2]]
    assert query.usage.tokens == plain.usage.tokens == 7
    assert mixed.embeddings == [[1, 2], [2, 3]] and mixed.usage.tokens == 9
    assert requests[0][0] == requests[1][0] == "/v1/embeddings"
    assert requests[0][2]["input"] == ["task: search result | query: anchor"]
    assert requests[1][2]["input"] == ["title: none | text: anchor"]
    assert requests[2][0] == f"/v1beta/models/{name}:batchEmbedContents"
    assert requests[2][2]["requests"][1]["content"]["parts"] == [
        {"inlineData": {"mimeType": "image/png", "data": IMAGE.base64_data}}
    ]


def test_sse_envelopes_keep_rate_limit_type(llm, wire):
    _, requests, replies = wire
    frame = sse("error", error={"type": "rate_limit_error"})
    replies.extend([(200, {}, frame), (200, {}, frame)])
    for model in ("qwen3.8-max", "claude-sonnet-4-6"):
        with pytest.raises(InvokeRateLimitError):
            invoke(llm, model, stream=True)
    assert [request[0] for request in requests] == ["/v1/chat/completions", "/v1/messages"]


def test_model_parameter_objects_cannot_carry_transport_fields(llm, wire):
    _, requests, _ = wire
    with pytest.raises(InvokeBadRequestError, match="Transport fields"):
        invoke(llm, "gpt-6-luna", {"reasoning_mode": {"api_key": "ignored"}})
    assert requests == []
