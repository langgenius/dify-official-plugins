"""Mistral reasoning content-chunk handling (no vendor calls).

Reasoning models (e.g. Mistral Large 4) return ``content`` as a list of chunks:
``{"type": "thinking", "thinking": [{"type": "text", "text": ...}]}`` followed by
``{"type": "text", "text": ...}``. When streaming, the thinking phase arrives as lists,
the transition delta carries both chunk types, and the answer phase is plain strings.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model.message import UserPromptMessage

from models.llm.llm import MistralAILargeLanguageModel

MODEL = "mistral-large-latest"
CREDENTIALS = {
    "mode": "chat",
    "endpoint_url": "https://api.mistral.ai/v1",
    "api_key": "test",
    "function_calling_type": "tool_call",
}
PROMPT = [UserPromptMessage(content="hi")]
USAGE = {"prompt_tokens": 3, "completion_tokens": 7, "total_tokens": 10}


def think(text, **extra):
    return {"type": "thinking", "thinking": [{"type": "text", "text": text}], **extra}


def text(value):
    return {"type": "text", "text": value}


def tool_call_delta():
    return {
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "index": 0,
                "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'},
            }
        ]
    }


@pytest.fixture
def llm():
    return MistralAILargeLanguageModel(model_schemas=[])


def stream_response(deltas, usage=USAGE):
    lines = []
    for i, delta in enumerate(deltas):
        last = i == len(deltas) - 1
        payload = {
            "id": "x",
            "model": MODEL,
            "choices": [{"index": 0, "delta": delta, "finish_reason": "stop" if last else None}],
        }
        if last and usage:
            payload["usage"] = usage
        lines.append("data: " + json.dumps(payload))
    lines.append("data: [DONE]")
    response = MagicMock()
    response.iter_lines.return_value = lines
    return response


def run_stream(llm, deltas, model=MODEL):
    return list(
        llm._handle_generate_stream_response(model, CREDENTIALS, stream_response(deltas), PROMPT)
    )


def joined(chunks):
    return "".join(
        c.delta.message.content for c in chunks if isinstance(c.delta.message.content, str)
    )


# ---------------------------------------------------------------- streaming


def test_stream_thinking_only(llm):
    chunks = run_stream(llm, [{"role": "assistant", "content": [think("Let me think.")]}])
    assert joined(chunks) == "<think>\nLet me think.\n</think>"


def test_stream_text_chunks_only(llm):
    chunks = run_stream(llm, [{"content": [text("Hello")]}, {"content": [text(" world")]}])
    assert joined(chunks) == "Hello world"


def test_stream_thinking_and_text_in_same_delta(llm):
    # Exact shape reported from production: closed thinking chunk + first text chunk.
    delta = {"content": [think("Reasoning.", closed=True), text("Answer.")]}
    chunks = run_stream(llm, [delta])
    assert joined(chunks) == "<think>\nReasoning.\n</think>Answer."


def test_stream_thinking_across_deltas_then_text(llm):
    deltas = [
        {"role": "assistant", "content": [think("Step 1. ")]},
        {"content": [think("Step 2. ")]},
        {"content": [think("Step 3.", closed=True), text("The")]},
        {"content": " answer"},
        {"content": " is 42."},
    ]
    chunks = run_stream(llm, deltas)
    assert joined(chunks) == "<think>\nStep 1. Step 2. Step 3.\n</think>The answer is 42."
    assert joined(chunks).count("<think>") == 1
    assert joined(chunks).count("</think>") == 1


def test_stream_closed_flag_on_intermediate_thinking_does_not_end_reasoning(llm):
    # Observed from the live API: `closed: true` also appears on intermediate thinking deltas.
    deltas = [
        {"role": "assistant", "content": ""},
        {"content": [think("a", closed=True)]},
        {"content": [think("b")]},
        {"content": [think("c", closed=True)]},
        {"content": [think("d", closed=True), text("391")]},
    ]
    chunks = run_stream(llm, deltas)
    assert joined(chunks) == "<think>\nabcd\n</think>391"


def test_stream_thinking_then_plain_string_text(llm):
    deltas = [{"content": [think("Hmm.")]}, {"content": "Plain answer."}]
    chunks = run_stream(llm, deltas)
    assert joined(chunks) == "<think>\nHmm.\n</think>Plain answer."


def test_stream_plain_string_content_unchanged(llm):
    chunks = run_stream(llm, [{"role": "assistant", "content": "Hello"}, {"content": " there"}])
    assert joined(chunks) == "Hello there"


def test_stream_thinking_then_tool_calls(llm):
    deltas = [{"content": [think("Need weather.")]}, {"content": "", **tool_call_delta()}]
    chunks = run_stream(llm, deltas)
    assert joined(chunks) == "<think>\nNeed weather.\n</think>"
    tool_calls = [tc for c in chunks for tc in c.delta.message.tool_calls]
    assert [tc.function.name for tc in tool_calls] == ["get_weather"]
    assert tool_calls[0].function.arguments == '{"city": "Paris"}'


def test_stream_empty_list_is_ignored(llm):
    chunks = run_stream(llm, [{"content": []}, {"content": [text("Hi")]}])
    assert joined(chunks) == "Hi"


def test_stream_empty_list_does_not_close_reasoning(llm):
    deltas = [{"content": [think("a")]}, {"content": []}, {"content": [think("b")]}]
    chunks = run_stream(llm, deltas)
    assert joined(chunks) == "<think>\nab\n</think>"


def test_stream_unknown_chunk_types_are_skipped(llm):
    deltas = [
        {"content": [think("x"), {"type": "reference", "reference_ids": [1]}]},
        {"content": [{"type": "something_new", "data": 1}, "not-a-dict", text("Hi")]},
    ]
    chunks = run_stream(llm, deltas)
    assert joined(chunks) == "<think>\nx\n</think>Hi"


def test_stream_usage_is_reported(llm):
    chunks = run_stream(llm, [{"content": [think("t", closed=True), text("a")]}])
    usage = chunks[-1].delta.usage
    assert usage.prompt_tokens == 3
    assert usage.completion_tokens == 7


@pytest.mark.parametrize(
    "delta, is_reasoning",
    [
        ({"content": "abc"}, False),
        ({"content": "abc"}, True),
        ({"content": ""}, True),
        ({"content": None}, False),
        ({"content": None}, True),
        ({"reasoning_content": "r"}, False),
        ({"reasoning_content": "r", "content": "c"}, True),
        ({}, True),
    ],
)
def test_wrap_non_list_content_matches_sdk(llm, delta, is_reasoning):
    expected = OAICompatLargeLanguageModel._wrap_thinking_by_reasoning_content(
        llm, dict(delta), is_reasoning
    )
    assert llm._wrap_thinking_by_reasoning_content(dict(delta), is_reasoning) == expected


# ------------------------------------------------------------ non-streaming


def blocking_response(content, usage=USAGE):
    response = MagicMock()
    response.json.return_value = {
        "id": "x",
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content, "tool_calls": None},
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
    }
    return response


def run_blocking(llm, content):
    return llm._handle_generate_response(MODEL, CREDENTIALS, blocking_response(content), PROMPT)


def test_blocking_thinking_and_text_chunks(llm):
    result = run_blocking(llm, [think("Reasoning.", closed=True), text("Answer.")])
    assert result.message.content == "<think>\nReasoning.\n</think>Answer."
    assert result.usage.prompt_tokens == 3
    assert result.usage.completion_tokens == 7


def test_blocking_text_chunks_only(llm):
    result = run_blocking(llm, [text("Hello"), text(" world")])
    assert result.message.content == "Hello world"


def test_blocking_unknown_chunk_types_are_skipped(llm):
    result = run_blocking(llm, [{"type": "reference", "reference_ids": [1]}, text("Hi")])
    assert result.message.content == "Hi"


def test_blocking_plain_string_unchanged(llm):
    result = run_blocking(llm, "Hello")
    assert result.message.content == "Hello"


# ----------------------------------------------------------------- invoke


@pytest.mark.parametrize(
    "model, params, expected",
    [
        ("magistral-medium-latest", {"reasoning_mode": True}, {"prompt_mode": "reasoning"}),
        ("magistral-medium-latest", {"reasoning_mode": False}, {"prompt_mode": None}),
        ("mistral-large-latest", {"reasoning_mode": True}, {"reasoning_mode": True}),
        ("mistral-large-latest", {"temperature": 0.3}, {"temperature": 0.3}),
    ],
)
def test_magistral_prompt_mode_mapping_unchanged(llm, model, params, expected):
    with patch.object(OAICompatLargeLanguageModel, "_invoke", return_value="ok") as parent:
        assert llm._invoke(model, {"api_key": "k"}, PROMPT, dict(params)) == "ok"
    assert parent.call_args.args[3] == expected
