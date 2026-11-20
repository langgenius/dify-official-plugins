from decimal import Decimal

from dify_plugin.entities.model.message import (
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from protocol_http import CREDENTIALS, PDF, TOOL, USER, contents, invoke, sse
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
    sent = requests[1][2]
    assert sent["thinking"] == {"type": "adaptive", "display": "summarized"}
    assistant, results = sent["messages"][-2:]
    assert assistant["content"][:2] == [signed, redacted]
    assert results["role"] == "user"
    assert [block["tool_use_id"] for block in results["content"]] == ["one", "two"]


def test_claude_json_object_mode_adds_a_format_instruction(llm, wire):
    _, requests, replies = wire
    expected = '{"answer":42,"extra":"allowed"}'
    replies.append((200, {}, claude_result([{"type": "text", "text": expected}])))
    chunks = invoke(
        llm,
        "claude-opus-4-6",
        {"response_format": "json_object"},
        messages=[SystemPromptMessage(content="Use concise values."), USER],
    )
    assert contents(chunks) == expected
    assert requests[0][0] == "/v1/messages"
    assert requests[0][2]["system"] == [
        {"type": "text", "text": "Use concise values."},
        {
            "type": "text",
            "text": "Return only a valid JSON object without Markdown or code fences.",
        },
    ]


def test_claude_code_block_mode_skips_prefill_on_4_6_and_sets_stop_sequences(llm, wire):
    _, requests, replies = wire
    replies.extend([(200, {}, claude_result())] * 3)
    invoke(llm, "claude-sonnet-4-6", {"response_format": "JSON", "temperature": 0.2})
    invoke(
        llm,
        "claude-opus-4-6",
        {"response_format": "JSON", "thinking": True, "thinking_budget": 1024, "max_tokens": 2048},
    )
    invoke(llm, "claude-sonnet-4-5-20250929", {"response_format": "JSON"})

    sonnet_46, opus_46, sonnet_45 = [req[2] for req in requests]
    assert sonnet_46["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "hello"}]}
    ]
    assert sonnet_46["temperature"] == 0.2
    assert sonnet_46["stop_sequences"] == ["```\n", "\n```"]

    assert opus_46["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]
    assert opus_46["thinking"] == {"type": "enabled", "budget_tokens": 1024}
    assert opus_46["stop_sequences"] == ["```\n", "\n```"]

    assert sonnet_45["messages"][-1] == {
        "role": "assistant",
        "content": [{"type": "text", "text": "\n```JSON"}],
    }
    assert sonnet_45["stop_sequences"] == ["```\n", "\n```"]


def test_claude_fable_5_2_validates_and_strips_speed_and_task_budget_and_scales_cache_reads(
    llm, wire
):
    import pytest
    from dify_plugin.errors.model import InvokeBadRequestError

    _, requests, replies = wire
    with pytest.raises((ValueError, InvokeBadRequestError)):
        invoke(llm, "claude-opus-4-7", {"task_budget": -1})
    assert requests == []
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
            (200, {}, claude_result()),
        ]
    )
    fast = invoke(llm, "claude-fable-5-2", {"speed": "fast", "task_budget": 64000})[-1].delta.usage
    standard = invoke(llm, "claude-fable-5-2", {"speed": "fast"})[-1].delta.usage
    invoke(llm, "claude-sonnet-4-6", {"speed": "fast"})
    sent = requests[0][2]
    assert "speed" not in sent
    assert "task_budget" not in sent.get("output_config", {})
    assert "anthropic-beta" not in requests[0][1]
    assert fast.prompt_tokens == 110
    assert (fast.prompt_unit_price, fast.completion_unit_price) == (Decimal("16"), Decimal("80"))
    assert fast.total_price == Decimal("0.00216")
    assert (standard.prompt_unit_price, standard.completion_unit_price) == (
        Decimal("8"),
        Decimal("40"),
    )
    assert standard.total_price == Decimal("0.00108")
    assert "speed" not in requests[2][2]
