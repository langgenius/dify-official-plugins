from __future__ import annotations

from types import SimpleNamespace

import pytest
from openai.types.responses import Response

from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    DeveloperPromptMessage,
    DocumentPromptMessageContent,
    ImagePromptMessageContent,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import (
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from models.llm import responses, stream as response_stream


def _visible(chunks) -> str:
    return "".join(chunk.delta.message.get_text_content() for chunk in chunks)


def _terminals(chunks) -> list:
    return [chunk for chunk in chunks if chunk.delta.finish_reason is not None]


def _message(text: str, *, refusal: bool = False) -> dict:
    part = (
        {"type": "refusal", "refusal": text}
        if refusal
        else {"type": "output_text", "text": text, "annotations": []}
    )
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [part],
    }


def _reasoning(summary: str, *, encrypted: str = "ciphertext") -> dict:
    return {
        "id": "rs_1",
        "type": "reasoning",
        "status": "completed",
        "encrypted_content": encrypted,
        "summary": [{"type": "summary_text", "text": summary}],
    }


def _function(index: int) -> dict:
    return {
        "id": f"fc_{index}",
        "type": "function_call",
        "call_id": f"call_{index}",
        "name": f"tool_{index}",
        "arguments": f'{{"value":{index}}}',
        "status": "completed",
    }


def test_multimodal_and_opaque_items_replay_in_exact_order() -> None:
    opaque = [_reasoning("prior summary"), _message("prior"), _function(1)]
    messages = [
        DeveloperPromptMessage(content="Follow policy"),
        UserPromptMessage(
            content=[
                TextPromptMessageContent(data="Question"),
                ImagePromptMessageContent(
                    url="https://example.com/image.png",
                    mime_type="image/png",
                    format="png",
                ),
                DocumentPromptMessageContent(
                    url="https://example.com/context.pdf",
                    mime_type="application/pdf",
                    format="pdf",
                ),
            ]
        ),
        AssistantPromptMessage(
            content="ignored",
            tool_calls=[responses.make_call("ignored", "ignored", "{}")],
            opaque_body={responses.OUTPUT_KEY: opaque},
        ),
        ToolPromptMessage(tool_call_id="call_1", content="tool result"),
        AssistantPromptMessage(
            content="next",
            tool_calls=[responses.make_call("call_2", "tool_2", "{}")],
        ),
    ]

    result = responses.input_items(messages)

    assert [(item["type"], item.get("role")) for item in result] == [
        ("message", "developer"),
        ("message", "user"),
        ("reasoning", None),
        ("message", "assistant"),
        ("function_call", None),
        ("function_call_output", None),
        ("message", "assistant"),
        ("function_call", None),
    ]
    assert result[1]["content"] == [
        {"type": "input_text", "text": "Question"},
        {
            "type": "input_image",
            "image_url": "https://example.com/image.png",
            "detail": "low",
        },
        {"type": "input_file", "file_url": "https://example.com/context.pdf"},
    ]
    assert result[2:5] == opaque
    assert result[5]["output"] == "tool result"
    result[2]["encrypted_content"] = "changed"
    assert opaque[0]["encrypted_content"] == "ciphertext"


def test_real_sdk_response_is_a_supported_happy_path(
    llm, mocker, prompt_messages
) -> None:
    response = Response.model_validate(
        {
            "id": "resp_sdk",
            "created_at": 1.0,
            "model": "gpt-5.6",
            "object": "response",
            "output": [_reasoning("Checked"), _message("Answer"), _function(1)],
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            "status": "completed",
            "usage": {
                "input_tokens": 13,
                "input_tokens_details": {
                    "cache_write_tokens": 0,
                    "cached_tokens": 0,
                },
                "output_tokens": 8,
                "output_tokens_details": {"reasoning_tokens": 3},
                "total_tokens": 21,
            },
        }
    )
    client = mocker.Mock()
    client.responses.create.return_value = response

    result = responses.generate(
        llm, client, "gpt-5.6", {}, prompt_messages, {}, None, None, None
    )

    assert result.message.content == "<think>\nChecked\n</think>\nAnswer"
    assert [call.id for call in result.message.tool_calls] == ["call_1"]
    assert result.message.opaque_body[responses.OUTPUT_KEY][0]["type"] == "reasoning"
    llm._calc_response_usage.assert_called_once_with("gpt-5.6", {}, 13, 8)


def test_non_stream_only_exposes_reasoning_summary(
    llm, mocker, prompt_messages, response_factory
) -> None:
    reasoning = _reasoning("Safe summary", encrypted="do-not-display")
    reasoning["content"] = [{"type": "reasoning_text", "text": "private raw reasoning"}]
    client = mocker.Mock()
    client.responses.create.return_value = response_factory(
        output=[reasoning, _message("Final")]
    )

    result = responses.generate(
        llm, client, "gpt-5.6", {}, prompt_messages, {}, None, None, None
    )

    assert result.message.content == "<think>\nSafe summary\n</think>\nFinal"
    assert "do-not-display" not in result.message.content
    assert "private raw reasoning" not in result.message.content


def test_stream_transitions_from_reasoning_to_text(
    invoke_stream, response_factory
) -> None:
    terminal = response_factory(output=[_reasoning("Plan"), _message("Answer")])
    chunks, fake, _ = invoke_stream(
        [
            {"type": "response.reasoning_summary_text.delta", "delta": "Plan"},
            {"type": "response.output_text.delta", "delta": "Answer"},
            {"type": "response.completed", "response": terminal},
        ]
    )

    assert _visible(chunks) == "<think>\nPlan\n</think>\nAnswer"
    assert len(_terminals(chunks)) == 1
    assert fake.closed


def test_reasoning_only_stream_closes_think_block(
    invoke_stream, response_factory
) -> None:
    terminal = response_factory(output=[_reasoning("Plan")])
    chunks, _, _ = invoke_stream(
        [
            {"type": "response.reasoning_summary_text.delta", "delta": "Plan"},
            {"type": "response.completed", "response": terminal},
        ]
    )

    assert _visible(chunks) == "<think>\nPlan\n</think>\n"
    assert len(_terminals(chunks)) == 1


def test_refusal_is_streamed_as_visible_text(invoke_stream, response_factory) -> None:
    terminal = response_factory(output=[_message("Cannot comply", refusal=True)])
    chunks, _, _ = invoke_stream(
        [
            {"type": "response.refusal.delta", "delta": "Cannot comply"},
            {"type": "response.completed", "response": terminal},
        ]
    )

    assert _visible(chunks) == "Cannot comply"
    assert len(_terminals(chunks)) == 1


def test_empty_and_unknown_events_are_ignored(invoke_stream, response_factory) -> None:
    terminal = response_factory()
    chunks, _, _ = invoke_stream(
        [
            {},
            {"type": "response.heartbeat"},
            {"type": "response.output_text.delta", "delta": ""},
            {"type": "response.completed", "response": terminal},
        ]
    )

    assert _visible(chunks) == ""
    assert len(chunks) == 1
    assert chunks[0].delta.finish_reason == "stop"


def test_interleaved_function_calls_follow_output_index_once(
    invoke_stream, response_factory
) -> None:
    terminal = response_factory(output=[])
    chunks, _, _ = invoke_stream(
        [
            {
                "type": "response.output_item.added",
                "output_index": 2,
                "item": {
                    "type": "function_call",
                    "call_id": "call_2",
                    "name": "tool_2",
                },
            },
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {
                    "type": "function_call",
                    "call_id": "call_0",
                    "name": "tool_0",
                },
            },
            {
                "type": "response.function_call_arguments.delta",
                "output_index": 2,
                "delta": '{"value":',
            },
            {
                "type": "response.function_call_arguments.delta",
                "output_index": 0,
                "delta": '{"value":',
            },
            {
                "type": "response.function_call_arguments.done",
                "output_index": 2,
                "arguments": '{"value":2}',
            },
            {
                "type": "response.function_call_arguments.done",
                "output_index": 0,
                "arguments": '{"value":0}',
            },
            {"type": "response.completed", "response": terminal},
        ]
    )

    assert len(chunks) == 1
    assert chunks[0].delta.finish_reason == "tool_calls"
    calls = chunks[0].delta.message.tool_calls
    assert [(call.id, call.function.arguments) for call in calls] == [
        ("call_0", '{"value":0}'),
        ("call_2", '{"value":2}'),
    ]


@pytest.mark.parametrize(
    ("deltas", "stops", "expected"),
    [
        (["before<ST", "OP>after"], ["<STOP>"], "before"),
        (["alpha END later STOP"], ["STOP", "END"], "alpha "),
        (["<STOP>after"], ["<STOP>"], ""),
    ],
)
def test_stop_sequences_never_leak(
    deltas, stops, expected, invoke_stream, response_factory
) -> None:
    raw = "".join(deltas)
    terminal = response_factory(output=[_message(raw), _function(1)])
    events = [
        {"type": "response.output_text.delta", "delta": delta} for delta in deltas
    ]
    events.append({"type": "response.completed", "response": terminal})

    chunks, _, _ = invoke_stream(events, stop=stops)

    assert _visible(chunks) == expected
    assert len(_terminals(chunks)) == 1
    assert chunks[-1].delta.finish_reason == "stop"
    assert chunks[-1].delta.message.tool_calls == []
    assert chunks[-1].delta.message.opaque_body is None


def test_stop_inside_streamed_reasoning_keeps_tags_balanced(
    invoke_stream, response_factory
) -> None:
    terminal = response_factory(output=[_reasoning("Plan STOP hidden")])
    chunks, _, _ = invoke_stream(
        [
            {
                "type": "response.reasoning_summary_text.delta",
                "delta": "Plan STOP hidden",
            },
            {"type": "response.completed", "response": terminal},
        ],
        stop=["STOP"],
    )

    assert _visible(chunks) == "<think>\nPlan \n</think>\n"
    assert chunks[-1].delta.finish_reason == "stop"


def test_stop_inside_nonstream_reasoning_keeps_tags_balanced(
    llm, mocker, prompt_messages, response_factory
) -> None:
    client = mocker.Mock()
    client.responses.create.return_value = response_factory(
        output=[_reasoning("Plan STOP hidden")]
    )

    result = responses.generate(
        llm,
        client,
        "gpt-5.6",
        {},
        prompt_messages,
        {},
        None,
        ["STOP"],
        None,
    )

    assert result.message.content == "<think>\nPlan \n</think>\n"
    assert result.message.opaque_body is None


@pytest.mark.parametrize(
    ("reason", "finish_reason"),
    [
        ("max_output_tokens", "length"),
        ("content_filter", "content_filter"),
        ("other", "incomplete"),
    ],
)
def test_incomplete_terminal_reason_is_preserved(
    reason, finish_reason, invoke_stream, response_factory
) -> None:
    terminal = response_factory(
        status="incomplete",
        incomplete_reason=reason,
        output=[_function(1)],
    )
    chunks, _, _ = invoke_stream(
        [{"type": "response.incomplete", "response": terminal}]
    )

    assert len(_terminals(chunks)) == 1
    assert chunks[-1].delta.finish_reason == finish_reason
    assert chunks[-1].delta.message.tool_calls == []


@pytest.mark.parametrize(
    ("code", "error"),
    [
        ("invalid_prompt", InvokeBadRequestError),
        ("rate_limit_exceeded", InvokeRateLimitError),
        ("server_error", InvokeServerUnavailableError),
        (None, InvokeServerUnavailableError),
    ],
)
def test_error_events_are_classified(code, error, invoke_stream) -> None:
    with pytest.raises(error, match=code or "response_failed"):
        invoke_stream([{"type": "error", "code": code, "message": "boom"}])


def test_failed_event_raises(invoke_stream, response_factory) -> None:
    terminal = response_factory(
        status="failed",
        error=SimpleNamespace(code="server_error", message="boom"),
    )
    with pytest.raises(InvokeServerUnavailableError, match="boom"):
        invoke_stream([{"type": "response.failed", "response": terminal}])


def test_stream_without_terminal_raises_and_closes(invoke_stream) -> None:
    with pytest.raises(InvokeConnectionError, match="without a terminal"):
        invoke_stream([{"type": "response.output_text.delta", "delta": "partial"}])


@pytest.mark.parametrize(("counts"), [(9, 4), (0, 0)])
def test_reported_usage_including_zero_is_used_once(
    counts, llm, invoke_stream, response_factory
) -> None:
    terminal = response_factory(
        output_text="done",
        usage=SimpleNamespace(input_tokens=counts[0], output_tokens=counts[1]),
    )
    chunks, _, _ = invoke_stream([{"type": "response.completed", "response": terminal}])

    assert len(_terminals(chunks)) == 1
    llm._calc_response_usage.assert_called_once_with(
        "gpt-5.6", {}, counts[0], counts[1]
    )


def test_missing_usage_falls_back_to_tokenizers_once(
    llm, mocker, invoke_stream, response_factory
) -> None:
    count_messages = mocker.patch(
        "models.llm.responses.tokens.count_messages", return_value=5
    )
    count_text = mocker.patch("models.llm.responses.tokens.count_text", return_value=3)
    terminal = response_factory(
        output=[_message("done"), _function(1)],
        usage=None,
    )

    chunks, _, _ = invoke_stream([{"type": "response.completed", "response": terminal}])

    assert len(_terminals(chunks)) == 1
    count_messages.assert_called_once()
    count_text.assert_called_once_with("gpt-5.6", 'done{"value":1}')
    llm._calc_response_usage.assert_called_once_with("gpt-5.6", {}, 5, 3)


def test_closing_partly_consumed_generator_closes_sdk_stream(
    llm, mocker, prompt_messages, response_factory, fake_stream_factory
) -> None:
    fake = fake_stream_factory(
        [
            {"type": "response.output_text.delta", "delta": "first"},
            {
                "type": "response.completed",
                "response": response_factory(output_text="first"),
            },
        ]
    )
    client = mocker.Mock()
    client.responses.create.return_value = fake
    generator = response_stream.generate(
        llm, client, "gpt-5.6", {}, prompt_messages, {}, None, None, None
    )

    assert next(generator).delta.message.content == "first"
    assert not fake.closed
    generator.close()

    assert fake.closed
