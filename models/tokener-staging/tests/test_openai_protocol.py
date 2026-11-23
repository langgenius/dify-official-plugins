import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from dify_plugin.entities.model.message import (
    AudioPromptMessageContent,
    DeveloperPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import (
    InvokeConnectionError,
)
from protocol_http import CREDENTIALS, PDF, TOOL, USER, chat_result, contents, invoke, sse
from protocol_http import llm as llm
from protocol_http import registry as registry
from protocol_http import wire as wire


def responses_output(text="ok"):
    return [
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}
    ]


def openai_result(output, status="completed", **extra):
    return {
        "status": status,
        "output": output,
        "usage": {"input_tokens": 9, "output_tokens": 4},
        **extra,
    }


def test_responses_replays_encrypted_output_and_forces_single_chunk(llm, wire):
    _, requests, replies = wire
    reason = {
        "type": "reasoning",
        "encrypted_content": "opaque",
        "summary": [{"type": "summary_text", "text": "reason"}],
    }
    output = [reason, *responses_output()]
    replies.extend([(200, {}, openai_result(output)), (200, {}, openai_result(responses_output()))])
    params = {
        "reasoning_effort": "max",
        "reasoning_mode": "pro",
        "reasoning_context": "all_turns",
        "reasoning_summary": "auto",
        "verbosity": "low",
        "service_tier": "flex",
        "temperature": 0.2,
        "top_p": 0.6,
        "enable_stream": False,
        "max_tokens": 99,
    }
    chunks = invoke(
        llm,
        "gpt-6-luna",
        params,
        stream=True,
        tools=[TOOL],
        messages=[DeveloperPromptMessage(content="policy"), UserPromptMessage(content=[PDF])],
    )
    assert len(chunks) == 1
    delta = chunks[0].delta
    assert delta.message.content == "<think>\nreason\n</think>\nok"
    assert delta.message.opaque_body == {"responses_output": output}
    assert delta.usage.total_tokens == 13
    assert requests[0][0] == "/v1/responses"
    sent = requests[0][2]
    assert sent["reasoning"] == {
        "effort": "max",
        "mode": "pro",
        "context": "all_turns",
        "summary": "auto",
    }
    assert (sent["text"], sent["service_tier"], sent["stream"], sent["store"]) == (
        {"verbosity": "low"},
        "flex",
        False,
        False,
    )
    assert sent["include"] == ["reasoning.encrypted_content"]
    assert not {"temperature", "top_p"} & sent.keys()
    assert sent["input"][0]["role"] == "developer"
    assert sent["input"][1]["content"] == [
        {"type": "input_file", "filename": "sample.pdf", "file_data": PDF.data}
    ]
    assert sent["tools"][0]["parameters"] == TOOL.parameters
    assert sent["max_output_tokens"] == 99
    invoke(llm, "gpt-6-luna", {"service_tier": "priority"}, messages=[USER, delta.message, USER])
    assert requests[1][2]["service_tier"] == "auto"
    assert requests[1][2]["input"][1:-1] == output


def test_responses_stream_handles_split_stop_and_drops_truncated_call(llm, wire):
    _, requests, replies = wire
    partial = {"type": "function_call", "call_id": "call", "name": "lookup", "arguments": '{"a":'}
    terminal = openai_result(
        [*responses_output("réply END spill"), partial],
        "incomplete",
        incomplete_details={"reason": "max_output_tokens"},
    )
    frames = (
        b": keepalive\r\n\r\n"
        + sse("response.output_text.delta", delta="réply E")
        + sse("response.output_text.delta", delta="ND spill")
        + sse("response.function_call_arguments.delta", delta='{"a":')
        + sse("response.incomplete", response=terminal)
    )
    replies.extend([(200, {}, frames), (200, {}, frames)])
    stopped = invoke(llm, "gpt-4o-mini", stream=True, stop=["END"], tools=[TOOL])
    assert contents(stopped) == "réply "
    assert stopped[-1].delta.finish_reason == "stop"
    assert not stopped[-1].delta.message.tool_calls
    assert stopped[-1].delta.message.opaque_body is None
    truncated = invoke(llm, "gpt-4o-mini", stream=True, tools=[TOOL])
    assert contents(truncated) == "réply END spill"
    assert truncated[-1].delta.finish_reason == "length"
    assert truncated[-1].delta.message.opaque_body == {
        "responses_output": responses_output("réply END spill")
    }
    assert not truncated[-1].delta.message.tool_calls
    assert all(item[0] == "/v1/responses" for item in requests)


@pytest.mark.parametrize("model_id", ["gpt-audio-1.5", "gpt-audio-mini-2025-12-15"])
def test_openai_audio_keeps_chat_with_audio_part(llm, wire, model_id):
    _, requests, replies = wire
    replies.append((200, {}, chat_result()))
    audio = AudioPromptMessageContent(format=".wav", mime_type="audio/wav", base64_data="UklGRg==")
    chunks = invoke(llm, model_id, messages=[UserPromptMessage(content=[audio])])
    assert contents(chunks) == "ok"
    assert requests[0][0] == "/v1/chat/completions"
    assert requests[0][2]["messages"][0]["content"] == [
        {"type": "input_audio", "input_audio": {"data": "UklGRg==", "format": "wav"}}
    ]


def test_openai_rejects_a_stream_without_terminal_event(llm, wire):
    _, _, replies = wire
    replies.append((200, {}, sse("response.output_text.delta", delta="partial")))
    with pytest.raises(InvokeConnectionError, match="terminal event"):
        invoke(llm, "gpt-4o-mini", stream=True)


@pytest.mark.parametrize("stream", [True, False])
def test_responses_stop_during_thinking_closes_the_display_tag(llm, wire, stream):
    _, _, replies = wire
    reason = {
        "type": "reasoning",
        "encrypted_content": "opaque",
        "summary": [{"type": "summary_text", "text": "thinking END hidden"}],
    }
    terminal = openai_result([reason, *responses_output()])
    frames = (
        sse("response.reasoning_summary_text.delta", delta="thinking E")
        + sse("response.reasoning_summary_text.delta", delta="ND hidden")
        + sse("response.completed", response=terminal)
    )
    replies.append((200, {}, frames if stream else terminal))
    chunks = invoke(llm, "gpt-6-luna", stream=stream, stop=["END"])
    assert contents(chunks) == "<think>\nthinking \n</think>\n"
    assert chunks[-1].delta.finish_reason == "stop"
    assert not chunks[-1].delta.message.opaque_body


GPT62_CACHE_DETAILS = {
    "cached_tokens": 4_000,
    "cache_write_tokens": 7_000,
    "cache_write_tokens_details": {"ttl_30m_tokens": 3_000, "ttl_12h_tokens": 4_000},
}


def _timestamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=UTC).timestamp() if value else None


def _gpt62_reply(route, stream, prompt, tier, created):
    if route == "responses":
        terminal = {
            "status": "completed",
            "output": responses_output(),
            "usage": {
                "input_tokens": prompt,
                "output_tokens": 7,
                "input_tokens_details": GPT62_CACHE_DETAILS,
            },
            "service_tier": tier,
            "created_at": created,
        }
        return sse("response.completed", response=terminal) if stream else terminal
    usage = {
        "prompt_tokens": prompt,
        "completion_tokens": 7,
        "prompt_tokens_details": GPT62_CACHE_DETAILS,
    }
    if not stream:
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": usage,
            "service_tier": tier,
            "created": created,
        }
    frames = [
        {"choices": [{"index": 0, "delta": {"content": "ok"}}], "created": created},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        {"choices": [], "usage": usage, "service_tier": tier},
    ]
    return b"".join(f"data: {json.dumps(frame)}\n\n".encode() for frame in frames) + (
        b"data: [DONE]\n\n"
    )


@pytest.mark.parametrize(
    ("route", "prompt", "tier", "created", "input_rate", "output_rate"),
    [
        ("responses", 272_000, "default", None, 1, 1),
        ("responses", 272_001, "priority", None, 4, 3),
        ("responses", 272_001, "ultrafast", "2027-03-01T07:59:59", 6, Decimal("4.5")),
        ("responses", 272_001, "ultrafast", "2027-03-01T08:00:00", 12, 9),
        ("chat", 272_000, "priority", None, 2, 2),
        ("chat", 272_001, "default", None, 2, Decimal("1.5")),
    ],
)
@pytest.mark.parametrize("stream", [False, True])
def test_gpt62_usage_charges_tier_long_context_and_cache_classes(
    llm, wire, route, stream, prompt, tier, created, input_rate, output_rate
):
    _, requests, replies = wire
    model = "gpt-6.2-astra"
    replies.append((200, {}, _gpt62_reply(route, stream, prompt, tier, _timestamp(created))))
    parameters = {"frequency_penalty": 0.5} if route == "chat" else {}
    usage = invoke(llm, model, parameters, stream=stream)[-1].delta.usage
    assert requests[0][0] == f"/v1/{'chat/completions' if route == 'chat' else 'responses'}"
    pricing = llm.get_model_schema(model, CREDENTIALS).pricing
    billable_prompt = prompt - 11_000 + 4_000 * Decimal("0.05") + 3_000 * Decimal("1.25")
    billable_prompt += 4_000 * Decimal("2.5")
    assert usage.prompt_tokens == prompt
    assert usage.prompt_price == pricing.input * input_rate * billable_prompt * pricing.unit
    assert usage.completion_price == pricing.output * output_rate * 7 * pricing.unit
    assert usage.total_price == usage.prompt_price + usage.completion_price
