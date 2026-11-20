import json
from unittest.mock import patch

import pytest
from dify_plugin.entities.model.llm import LLMResultChunk, LLMResultChunkDelta, LLMUsage
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    ToolPromptMessage,
    UserPromptMessage,
)
from requests import Response

from models.llm.llm import OpenAILargeLanguageModel


def _chunk(content, **delta):
    return LLMResultChunk(
        model="test-model",
        delta=LLMResultChunkDelta(
            index=0, message=AssistantPromptMessage(content=content), **delta
        ),
    )


@pytest.mark.parametrize("effort", [None, "none", "low"])
@pytest.mark.parametrize("compatibility_mode", ["strict", "extended"])
@pytest.mark.parametrize("support", ["supported", "only_thinking_supported"])
def test_thinking_enabled_does_not_wrap_plain_answer_after_tool(
    effort, compatibility_mode, support
):
    model = OpenAILargeLanguageModel(model_schemas=[])
    chunks = [_chunk("42"), _chunk("", finish_reason="stop", usage=LLMUsage.empty_usage())]
    parameters = {"enable_thinking": True}
    if effort is not None:
        parameters["reasoning_effort"] = effort
    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        return_value=iter(chunks),
    ):
        result = list(
            model._invoke(
                model="test-model",
                credentials={
                    "mode": "chat",
                    "agent_thought_support": support,
                    "compatibility_mode": compatibility_mode,
                },
                prompt_messages=[
                    UserPromptMessage(content="What is the result?"),
                    AssistantPromptMessage(
                        content="",
                        tool_calls=[
                            AssistantPromptMessage.ToolCall(
                                id="call_test",
                                type="function",
                                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                    name="calculate", arguments="{}"
                                ),
                            )
                        ],
                    ),
                    ToolPromptMessage(content="42", tool_call_id="call_test"),
                ],
                model_parameters=parameters,
                stream=True,
            )
        )

    assert result == chunks
    assert "".join(c.delta.message.content for c in result) == "42"
    assert result[-1].delta.finish_reason == "stop"
    assert result[-1].delta.usage == LLMUsage.empty_usage()


@pytest.mark.parametrize(
    "text",
    [
        "42",
        '{"answer":42}',
        "The closing tag is </think>.",
        '{"tag":"</think>"}',
        "Example:\n```\n</think>\n```\nDone.",
        "Example:\n~~~\n</think>\n~~~\nDone.",
        "A literal tag:\n</think> is not a delimiter.",
        "<th",
        " \n",
        "",
    ],
)
@pytest.mark.parametrize("character_chunks", [False, True])
def test_unconfirmed_reasoning_is_preserved(text, character_chunks):
    pieces = list(text) if character_chunks else [text]
    chunks = [_chunk(piece) for piece in pieces]

    result = list(OpenAILargeLanguageModel._restore_prefilled_think_stream(iter(chunks)))

    assert result == chunks
    assert "".join(c.delta.message.content for c in result) == text


@pytest.mark.parametrize(
    "reasoning",
    [
        "reasoning",
        "```\n</think>\n```\nreal reasoning",
        "~~~\n</think>\n~~~\nreal reasoning",
        "```\n<think>\n```\nreal reasoning",
        "~~~\n<think>\n~~~\nreal reasoning",
    ],
)
@pytest.mark.parametrize("suffix", ["\nanswer", ""])
def test_restore_only_after_a_real_closing_delimiter(reasoning, suffix):
    text = reasoning + "\n</think>" + suffix
    chunks = [_chunk(piece) for piece in text]

    result = list(OpenAILargeLanguageModel._restore_prefilled_think_stream(iter(chunks)))

    assert "".join(c.delta.message.content for c in result) == "<think>\n" + text


def test_explicit_thinking_stream_is_not_buffered_until_completion():
    def stream():
        yield _chunk("<th")
        yield _chunk("ink>reasoning")
        raise AssertionError("The consumer has not requested the rest of the stream yet")

    result = OpenAILargeLanguageModel._restore_prefilled_think_stream(stream())

    assert next(result).delta.message.content == "<th"
    assert next(result).delta.message.content == "ink>reasoning"
    result.close()


def test_restored_stream_resumes_before_the_answer_completes():
    def stream():
        yield _chunk("reasoning\n</think>\n")
        yield _chunk("answer")
        raise AssertionError("The consumer has not requested the rest of the stream yet")

    result = OpenAILargeLanguageModel._restore_prefilled_think_stream(stream())

    assert next(result).delta.message.content == "<think>\nreasoning\n</think>\n"
    assert next(result).delta.message.content == "answer"
    result.close()


def test_tool_only_stream_preserves_tool_calls_and_metadata():
    chunk = _chunk("", finish_reason="tool_calls", usage=LLMUsage.empty_usage())
    chunk.delta.message.tool_calls = [
        AssistantPromptMessage.ToolCall(
            id="call_test",
            type="function",
            function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                name="calculate", arguments="{}"
            ),
        )
    ]
    before = chunk.model_dump()

    result = list(OpenAILargeLanguageModel._restore_prefilled_think_stream(iter([chunk])))

    assert len(result) == 1
    assert result[0].model_dump() == before


def _sse_response(deltas, finish_reason="stop"):
    frames = [
        {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]} for delta in deltas
    ]
    frames.append(
        {
            "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
    )
    response = Response()
    response.status_code = 200
    response.encoding = "utf-8"
    response._content = (
        "".join(f"data: {json.dumps(frame)}\n\n" for frame in frames) + "data: [DONE]\n\n"
    ).encode()
    response._content_consumed = True
    return response


@pytest.mark.parametrize(
    ("deltas", "expected"),
    [
        ([{"reasoning_content": ""}, {"content": "4"}, {"content": "2"}], "42"),
        (
            [{"reasoning_content": "reasoning"}, {"content": "42"}],
            "<think>\nreasoning\n</think>42",
        ),
        (
            [{"content": "reasoning\n</th"}, {"content": "ink>\n"}, {"content": "42"}],
            "<think>\nreasoning\n</think>\n42",
        ),
    ],
)
def test_real_sdk_stream_parser(deltas, expected):
    model = OpenAILargeLanguageModel(model_schemas=[])
    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.requests.post",
        return_value=_sse_response(deltas),
    ) as post:
        chunks = list(
            model._invoke(
                model="test-model",
                credentials={
                    "endpoint_url": "https://api.example.com/v1/",
                    "mode": "chat",
                    "agent_thought_support": "supported",
                    "compatibility_mode": "strict",
                },
                prompt_messages=[UserPromptMessage(content="Return the answer.")],
                model_parameters={"enable_thinking": True, "reasoning_effort": "none"},
                stream=True,
            )
        )

    assert "".join(c.delta.message.content for c in chunks) == expected
    assert chunks[-1].delta.finish_reason == "stop"
    assert chunks[-1].delta.usage.total_tokens == 15
    request = json.loads(post.call_args.kwargs["data"])
    assert request["stream"] is True
    assert request["reasoning_effort"] == "none"
    assert "enable_thinking" not in request


def test_real_sdk_streaming_tool_round_trip_without_reasoning():
    model = OpenAILargeLanguageModel(model_schemas=[])
    credentials = {
        "endpoint_url": "https://api.example.com/v1/",
        "mode": "chat",
        "agent_thought_support": "supported",
        "function_calling_type": "tool_call",
    }
    messages = [UserPromptMessage(content="Calculate the answer.")]
    tool_response = _sse_response(
        [
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_test",
                        "type": "function",
                        "function": {"name": "calculate", "arguments": '{"value":'},
                    }
                ]
            },
            {"tool_calls": [{"index": 0, "function": {"arguments": "42}"}}]},
        ],
        finish_reason="tool_calls",
    )
    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.requests.post",
        side_effect=[tool_response, _sse_response([{"content": "42"}])],
    ) as post:
        chunks = list(
            model._invoke(
                model="test-model",
                credentials=credentials,
                prompt_messages=messages,
                model_parameters={"enable_thinking": True, "reasoning_effort": "low"},
                tools=[
                    PromptMessageTool(
                        name="calculate",
                        description="Return a value.",
                        parameters={"type": "object", "properties": {"value": {"type": "integer"}}},
                    )
                ],
                stream=True,
            )
        )
        calls = [call for chunk in chunks for call in chunk.delta.message.tool_calls]
        assert len(calls) == 1
        assert calls[0].id == "call_test"
        assert calls[0].function.arguments == '{"value":42}'
        assert chunks[-1].delta.finish_reason == "tool_calls"
        messages.extend(
            [
                AssistantPromptMessage(content="", tool_calls=calls),
                ToolPromptMessage(content="42", tool_call_id=calls[0].id),
            ]
        )
        answer = list(
            model._invoke(
                model="test-model",
                credentials=credentials,
                prompt_messages=messages,
                model_parameters={"enable_thinking": True, "reasoning_effort": "low"},
                stream=True,
            )
        )

    assert "".join(c.delta.message.content for c in answer) == "42"
    assert answer[-1].delta.finish_reason == "stop"
    assert answer[-1].delta.usage.total_tokens == 15
    request = json.loads(post.call_args.kwargs["data"])
    assert request["messages"][-1] == {"role": "tool", "content": "42", "tool_call_id": "call_test"}


def test_long_ambiguous_stream_scans_each_line_once():
    model = OpenAILargeLanguageModel(model_schemas=[])
    text = "abcdefgh" * 16000
    scanned = 0
    fence_pattern = model._FENCE_PATTERN
    closing_pattern = model._PREFILLED_THINK_END

    class CountedPattern:
        def __init__(self, pattern):
            self.pattern = pattern

        def match(self, content):
            nonlocal scanned
            scanned += len(content)
            return self.pattern.match(content)

        def fullmatch(self, content):
            nonlocal scanned
            scanned += len(content)
            return self.pattern.fullmatch(content)

        def search(self, content, pos=0):
            nonlocal scanned
            scanned += len(content)
            return self.pattern.search(content, pos)

        def finditer(self, content):
            nonlocal scanned
            scanned += len(content)
            return self.pattern.finditer(content)

    with (
        patch.object(OpenAILargeLanguageModel, "_FENCE_PATTERN", CountedPattern(fence_pattern)),
        patch.object(
            OpenAILargeLanguageModel, "_PREFILLED_THINK_END", CountedPattern(closing_pattern)
        ),
    ):
        chunks = (_chunk(text[i : i + 8]) for i in range(0, len(text), 8))
        result = list(model._restore_prefilled_think_stream(chunks))

    assert "".join(c.delta.message.content for c in result) == text
    assert scanned <= 2 * len(text)
