from decimal import Decimal

import pytest
from dify_plugin.entities.model.message import (
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from protocol_http import CREDENTIALS, PDF, TOOL, USER, contents, invoke, sse, with_fixture_schema
from protocol_http import llm as llm
from protocol_http import registry as registry
from protocol_http import wire as wire

from models.llm._wire import tool_call


def claude_result(content=None, **extra):
    return {
        "content": content or [{"type": "text", "text": "ok"}],
        "usage": {"input_tokens": 10, "output_tokens": 1},
        "stop_reason": "end_turn",
        **extra,
    }


def test_claude_strips_tags_caps_cache_breakpoints_and_counts_tokens(llm, wire):
    _, requests, replies = wire
    replies.extend(
        [(200, {}, claude_result()), (200, {}, claude_result()), (200, {}, {"input_tokens": 99})]
    )
    model = "claude-sonnet-4-6"
    messages = [
        SystemPromptMessage(
            content="A <cache>one</cache> <cache>two</cache> <cache>three</cache>"
            " <cache>four</cache> <cache>five</cache>"
        ),
        UserPromptMessage(content=[PDF]),
    ]
    invoke(
        llm,
        model,
        {
            "prompt_caching_system_message": True,
            "prompt_caching_ttl": "1h",
            "temperature": 0.5,
            "top_k": 4,
        },
        messages=messages,
    )
    invoke(llm, model, messages=messages)
    assert llm.get_num_tokens(model, CREDENTIALS, messages) == 99
    assert [r[0] for r in requests] == ["/v1/messages", "/v1/messages", "/v1/messages/count_tokens"]
    sent = requests[0][2]
    points = [part["cache_control"] for part in sent["system"] if "cache_control" in part]
    assert points == [{"type": "ephemeral"}] * 4
    assert sent["temperature"] == 0.5 and sent["top_k"] == 4
    assert sent["messages"][0]["content"] == [
        {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": PDF.base64_data},
        }
    ]
    for _, _, sent in requests:
        assert "".join(b["text"] for b in sent["system"]) == "A one two three four five"
    assert requests[1][2]["system"] == [{"type": "text", "text": "A one two three four five"}]


def test_claude_stream_replays_signed_and_redacted_thinking_with_tool_results(llm, wire):
    _, requests, replies = wire
    signed = {"type": "thinking", "thinking": "reason", "signature": "abc"}
    redacted = {"type": "redacted_thinking", "data": "hidden"}
    frames = b"".join(
        [
            sse(
                "message_start",
                message={"usage": {"input_tokens": 11, "cache_read_input_tokens": 7}},
            ),
            sse(
                "content_block_start",
                index=0,
                content_block={"type": "thinking", "thinking": "", "signature": ""},
            ),
            sse(
                "content_block_delta",
                index=0,
                delta={"type": "thinking_delta", "thinking": "reason"},
            ),
            sse(
                "content_block_delta", index=0, delta={"type": "signature_delta", "signature": "a"}
            ),
            sse(
                "content_block_delta", index=0, delta={"type": "signature_delta", "signature": "bc"}
            ),
            sse("content_block_stop", index=0),
            sse("content_block_start", index=1, content_block=redacted),
            sse("content_block_stop", index=1),
            sse(
                "content_block_start",
                index=2,
                content_block={"type": "tool_use", "id": "one", "name": "lookup", "input": {}},
            ),
            sse(
                "content_block_delta",
                index=2,
                delta={"type": "input_json_delta", "partial_json": '{"limit":1}'},
            ),
            sse("content_block_stop", index=2),
            sse("message_delta", delta={"stop_reason": "tool_use"}, usage={"output_tokens": 3}),
            sse("message_stop"),
        ]
    )
    replies.extend([(200, {}, frames), (200, {}, claude_result())])
    model = "claude-opus-4-7"
    params = {"thinking": True, "thinking_display": "summarized", "effort": "high"}
    chunks = invoke(llm, model, params, stream=True, tools=[TOOL])
    final = chunks[-1].delta
    assert contents(chunks) == "<think>\nreason\n</think>\n\n"
    assert final.message.opaque_body == {"anthropic_thinking": [signed, redacted]}
    assert final.finish_reason == "tool_calls"
    assert final.usage.total_tokens == 14
    final.message.tool_calls.append(tool_call("two", "lookup", {"limit": 2}))
    invoke(
        llm,
        model,
        params,
        tools=[TOOL],
        messages=[
            USER,
            final.message,
            ToolPromptMessage(tool_call_id="one", content="first"),
            ToolPromptMessage(tool_call_id="two", content="second"),
        ],
    )
    assert requests[0][1]["anthropic-version"]
    assert requests[0][2]["messages"][0]["content"] == [{"type": "text", "text": "hello"}]
    sent = requests[1][2]
    assert sent["thinking"] == {"type": "adaptive", "display": "summarized"}
    assistant, results = sent["messages"][-2:]
    assert assistant["content"][:2] == [signed, redacted]
    assert results["role"] == "user"
    assert [block["tool_use_id"] for block in results["content"]] == ["one", "two"]


def test_claude_fable_5_2_prices_speed_and_cache_reads(llm, wire, monkeypatch):
    llm = with_fixture_schema(llm, monkeypatch, "claude-fable-5-2")
    _, _, replies = wire
    replies.extend(
        [
            (
                200,
                {},
                claude_result(
                    usage={
                        "input_tokens": 100,
                        "cache_read_input_tokens": 400,
                        "output_tokens": 5,
                        "speed": "fast",
                    }
                ),
            ),
            (
                200,
                {},
                claude_result(
                    usage={
                        "input_tokens": 100,
                        "cache_read_input_tokens": 400,
                        "output_tokens": 5,
                        "speed": "standard",
                    }
                ),
            ),
        ]
    )
    fast = invoke(llm, "claude-fable-5-2", {"speed": "fast", "task_budget": 64000})[-1].delta.usage
    standard = invoke(llm, "claude-fable-5-2", {"speed": "fast"})[-1].delta.usage
    assert fast.prompt_tokens == 110
    assert (fast.prompt_unit_price, fast.completion_unit_price) == (Decimal("16"), Decimal("80"))
    assert fast.total_price == Decimal("0.00216")
    assert (standard.prompt_unit_price, standard.completion_unit_price) == (
        Decimal("8"),
        Decimal("40"),
    )
    assert standard.total_price == Decimal("0.00108")


def _claude_reply(stream, usage, *, text="ok", reason="end_turn", category=None):
    details = {"type": "refusal", "category": category} if reason == "refusal" else None
    content = [{"type": "text", "text": text}] if text else []
    if not stream:
        return {"content": content, "usage": usage, "stop_reason": reason, "stop_details": details}
    frames = [sse("message_start", message={"usage": usage})]
    if text:
        frames += [
            sse("content_block_start", index=0, content_block={"type": "text", "text": ""}),
            sse("content_block_delta", index=0, delta={"type": "text_delta", "text": text}),
            sse("content_block_stop", index=0),
        ]
    frames += [
        sse(
            "message_delta",
            delta={"stop_reason": reason, "stop_details": details},
            usage={"output_tokens": usage["output_tokens"]},
        ),
        sse("message_stop"),
    ]
    return b"".join(frames)


def _claude_usage(llm, wire, stream, model, usage, **reply):
    _, _, replies = wire
    replies.append((200, {}, _claude_reply(stream, usage, **reply)))
    return invoke(llm, model, stream=stream)[-1].delta.usage


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    ("category", "text", "billed"),
    [
        (None, "", False),
        ("cyber", "", False),
        ("bio", "", True),
        ("frontier_llm", "", True),
        ("reasoning_extraction", "", True),
        ("cyber", "Partial reply", True),
    ],
)
def test_claude_refusal_charges_follow_stop_details(llm, wire, stream, category, text, billed):
    tokens = {"input_tokens": 1250, "output_tokens": int(bool(text))}
    usage = _claude_usage(
        llm, wire, stream, "claude-opus-4-6", tokens, text=text, reason="refusal", category=category
    )
    baseline = _claude_usage(llm, wire, stream, "claude-opus-4-6", tokens, text=text)
    assert (usage.prompt_tokens, usage.completion_tokens) == (1250, int(bool(text)))
    assert baseline.total_price > 0
    assert usage.total_price == (baseline.total_price if billed else 0)


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    ("model", "multiplier"), [("claude-opus-4-6", "1.1"), ("claude-sonnet-4-5", "1")]
)
def test_claude_us_inference_geo_surcharge_starts_at_4_6(llm, wire, stream, model, multiplier):
    tokens = {"input_tokens": 1000, "output_tokens": 2}
    us = _claude_usage(llm, wire, stream, model, {**tokens, "inference_geo": "us"})
    baseline = _claude_usage(llm, wire, stream, model, tokens)
    assert us.prompt_unit_price == baseline.prompt_unit_price * Decimal(multiplier)
    assert us.completion_unit_price == baseline.completion_unit_price * Decimal(multiplier)
    assert us.total_price == baseline.total_price * Decimal(multiplier)


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(("reads", "multiplier"), [(100, 1), (101, 5)])
def test_claude_haiku_5_5_long_input_rate_counts_cached_input(llm, wire, stream, reads, multiplier):
    model = "claude-haiku-5-5"
    usage = _claude_usage(
        llm,
        wire,
        stream,
        model,
        {"input_tokens": 99_900, "cache_read_input_tokens": reads, "output_tokens": 1},
    )
    pricing = llm.get_model_schema(model, CREDENTIALS).pricing
    assert usage.prompt_unit_price == pricing.input * multiplier
    assert usage.completion_unit_price == pricing.output * multiplier


@pytest.mark.parametrize("mode", ["json_object", "JSON", "XML"])
def test_claude_format_request_preserves_user_instructions(llm, wire, mode):
    _, requests, replies = wire
    replies.append((200, {}, claude_result()))
    invoke(
        llm,
        "claude-opus-4-6",
        {"response_format": mode},
        messages=[SystemPromptMessage(content="Use concise values."), USER],
    )
    body = requests[0][2]
    instructions = "\n".join(part["text"] for part in body["system"])
    assert "Use concise values." in instructions
    assert ("XML" if mode == "XML" else "JSON") in instructions
    assert body["messages"][0]["content"] == [{"type": "text", "text": "hello"}]
