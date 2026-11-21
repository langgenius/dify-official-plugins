import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import PromptMessageTool, UserPromptMessage
from dify_plugin.errors.model import InvokeServerUnavailableError

from models._credentials import ENDPOINT_URL
from models.llm.llm import TokenerLargeLanguageModel

MODEL = "deepseek-v4-pro"


def _model() -> TokenerLargeLanguageModel:
    schema = yaml.safe_load(Path("models/llm/deepseek-v4-pro.yaml").read_text(encoding="utf-8"))
    return TokenerLargeLanguageModel(model_schemas=[AIModelEntity(**schema)])


def _stream_response(events: list[dict]) -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response.encoding = "utf-8"
    response.iter_lines = Mock(
        return_value=[
            f"data: {json.dumps(event)}"
            for event in [
                *events,
                {
                    "choices": [{"delta": {}, "finish_reason": "tool_calls"}],
                    "usage": {
                        "prompt_tokens": 13,
                        "completion_tokens": 7,
                        "total_tokens": 20,
                    },
                },
            ]
        ]
    )
    response._content = ("\n\n".join(response.iter_lines.return_value) + "\n\n").encode()
    response._content_consumed = True
    return response


def _tool_delta(index: int, **fields: object) -> dict:
    function = fields.pop("function", {})
    return {"index": index, **fields, "function": function}


def _stream_event(tool_calls: list[dict], content: str | None = None) -> dict:
    delta = {"tool_calls": tool_calls}
    if content is not None:
        delta["content"] = content
    return {"choices": [{"delta": delta, "finish_reason": None}]}


def _invoke_stream(events: list[dict], model=None) -> list:
    response = _stream_response(events)
    with patch("requests.post", return_value=response):
        return list(
            (model or _model()).invoke(
                MODEL,
                {
                    "api_key": "test-key",
                    "endpoint_url": ENDPOINT_URL,
                    "mode": "chat",
                    "function_calling_type": "tool_call",
                },
                [UserPromptMessage(content="Run both tools")],
                {"max_tokens": 32, "enable_thinking": False},
                tools=[
                    PromptMessageTool(name="foo", description="", parameters={"type": "object"}),
                    PromptMessageTool(name="bar", description="", parameters={"type": "object"}),
                ],
                stream=True,
            )
        )


def _assert_stream_result(chunks: list, expected: dict[str, tuple[str, str]]) -> None:
    tool_chunk = next(chunk for chunk in chunks if chunk.delta.message.tool_calls)
    tool_calls = {
        call.id: (call.function.name, call.function.arguments)
        for call in tool_chunk.delta.message.tool_calls
    }
    assert len(tool_chunk.delta.message.tool_calls) == len(expected)
    assert tool_calls == expected
    assert (
        "".join(
            chunk.delta.message.content or ""
            for chunk in chunks
            if not chunk.delta.message.tool_calls
        )
        == "answer"
    )
    final_delta = chunks[-1].delta
    assert final_delta.finish_reason == "tool_calls"
    assert final_delta.usage.prompt_tokens == 13
    assert final_delta.usage.completion_tokens == 7
    assert final_delta.usage.total_tokens == 20


def test_stream_parallel_tool_arguments_follow_tool_index() -> None:
    chunks = _invoke_stream(
        [
            _stream_event(
                [
                    _tool_delta(
                        0,
                        id="call0",
                        type="function",
                        function={"name": "foo", "arguments": '{"x":'},
                    ),
                    _tool_delta(
                        1,
                        id="call1",
                        type="function",
                        function={"name": "bar", "arguments": '{"y":'},
                    ),
                ],
                content="answer",
            ),
            _stream_event([_tool_delta(0, function={"arguments": "1}"})]),
            _stream_event([_tool_delta(1, function={"arguments": "2}"})]),
        ]
    )

    _assert_stream_result(
        chunks,
        {"call0": ("foo", '{"x":1}'), "call1": ("bar", '{"y":2}')},
    )


def test_stream_tool_name_can_arrive_after_id_and_arguments() -> None:
    chunks = _invoke_stream(
        [
            _stream_event(
                [
                    _tool_delta(
                        0,
                        id="call0",
                        type="function",
                        function={"arguments": '{"x":1}'},
                    )
                ],
                content="answer",
            ),
            _stream_event([_tool_delta(0, function={"name": "foo"})]),
        ]
    )

    _assert_stream_result(chunks, {"call0": ("foo", '{"x":1}')})


def test_stream_parallel_tool_fields_can_arrive_out_of_order() -> None:
    chunks = _invoke_stream(
        [
            _stream_event(
                [
                    _tool_delta(1, type="function", function={"arguments": '{"y":'}),
                    _tool_delta(0, type="function", function={"arguments": '{"x":'}),
                ],
                content="answer",
            ),
            _stream_event([_tool_delta(0, id="call0")]),
            _stream_event([_tool_delta(1, id="call1")]),
            _stream_event([_tool_delta(0, function={"name": "foo"})]),
            _stream_event([_tool_delta(1, function={"name": "bar"})]),
            _stream_event([_tool_delta(0, function={"arguments": "1}"})]),
            _stream_event([_tool_delta(1, function={"arguments": "2}"})]),
        ]
    )

    _assert_stream_result(
        chunks,
        {"call0": ("foo", '{"x":1}'), "call1": ("bar", '{"y":2}')},
    )


def test_non_stream_parallel_tool_calls_preserve_complete_values() -> None:
    response = requests.Response()
    response.status_code = 200
    response.encoding = "utf-8"
    response._content = json.dumps(
        {
            "id": "response-id",
            "model": MODEL,
            "choices": [
                {
                    "message": {
                        "content": "answer",
                        "tool_calls": [
                            {
                                "id": "call0",
                                "type": "function",
                                "function": {"name": "foo", "arguments": '{ "x": 1 }'},
                            },
                            {
                                "id": "call1",
                                "type": "function",
                                "function": {"name": "bar", "arguments": '{ "y": 2 }'},
                            },
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {
                "prompt_tokens": 13,
                "completion_tokens": 7,
                "total_tokens": 20,
            },
        }
    ).encode()

    with patch("requests.post", return_value=response):
        chunks = list(
            _model().invoke(
                MODEL,
                {"api_key": "test-key"},
                [UserPromptMessage(content="Run both tools")],
                {"max_tokens": 32, "enable_thinking": False},
                tools=[
                    PromptMessageTool(name="foo", description="", parameters={"type": "object"}),
                    PromptMessageTool(name="bar", description="", parameters={"type": "object"}),
                ],
                stream=False,
            )
        )

    result = chunks[0].delta
    assert result.message.content == "answer"
    assert {
        call.id: (call.function.name, call.function.arguments) for call in result.message.tool_calls
    } == {
        "call0": ("foo", '{ "x": 1 }'),
        "call1": ("bar", '{ "y": 2 }'),
    }
    assert result.usage.prompt_tokens == 13
    assert result.usage.completion_tokens == 7
    assert result.usage.total_tokens == 20


def test_stream_initial_tool_id_without_function_is_preserved() -> None:
    chunks = _invoke_stream(
        [
            _stream_event([{"index": 0, "id": "call0", "type": "function"}], "answer"),
            _stream_event([_tool_delta(0, function={"arguments": '{"x":1}'})]),
            _stream_event([_tool_delta(0, function={"name": "foo"})]),
        ]
    )
    _assert_stream_result(chunks, {"call0": ("foo", '{"x":1}')})


def test_stream_reasoning_and_usage_only_chunks_are_preserved() -> None:
    chunks = _invoke_stream(
        [
            {"choices": [{"delta": {"reasoning_content": "reason"}}]},
            _stream_event(
                [_tool_delta(0, id="call0", function={"name": "foo", "arguments": "{}"})],
                "answer",
            ),
            {"choices": [], "usage": {"prompt_tokens": 13, "completion_tokens": 7}},
        ]
    )
    assert "".join(chunk.delta.message.content or "" for chunk in chunks) == (
        "<think>\nreason\n</think>answer"
    )
    assert chunks[-2].delta.message.tool_calls[0].id == "call0"
    assert chunks[-1].delta.finish_reason == "tool_calls"
    assert chunks[-1].delta.usage.total_tokens == 20


def test_stream_without_indices_keeps_legacy_single_tool_behavior() -> None:
    chunks = _invoke_stream(
        [
            _stream_event(
                [{"id": "call0", "function": {"name": "foo", "arguments": '{"x":'}}],
                "answer",
            ),
            _stream_event([{"function": {"arguments": "1}"}}]),
        ]
    )
    _assert_stream_result(chunks, {"call0": ("foo", '{"x":1}')})


def test_stream_keepalive_and_finish_preserve_collected_tools() -> None:
    response = _stream_response([])
    response.iter_lines = Mock(
        return_value=[
            ": keepalive",
            'data: {"choices": [{"delta": {"content": "answer", "tool_calls": '
            '[{"index": 0, "id": "call0", "function": {"name": "foo", "arguments": "{}"}}]}, '
            '"finish_reason": "tool_calls"}], '
            '"usage": {"prompt_tokens": 13, "completion_tokens": 7}}',
        ]
    )
    response._content = ("\n\n".join(response.iter_lines.return_value) + "\n\n").encode()
    with patch("requests.post", return_value=response):
        chunks = list(
            _model().invoke(
                MODEL,
                {"api_key": "test-key"},
                [UserPromptMessage(content="Run tools")],
                {},
                stream=True,
            )
        )
    assert any(chunk.delta.finish_reason == "tool_calls" for chunk in chunks)
    assert [
        (call.id, call.function.name, call.function.arguments)
        for chunk in chunks
        for call in chunk.delta.message.tool_calls
    ] == [("call0", "foo", "{}")]
    assert chunks[-1].delta.usage.total_tokens == 20


def test_stream_upstream_error_is_propagated() -> None:
    response = _stream_response([])
    response.iter_lines = Mock(return_value=['data: {"error": "upstream rejected request"}'])
    response._content = b'data: {"error": "upstream rejected request"}\n\n'
    with patch("requests.post", return_value=response), pytest.raises(InvokeServerUnavailableError):
        list(
            _model().invoke(
                MODEL,
                {"api_key": "test-key"},
                [UserPromptMessage(content="Run tools")],
                {},
                stream=True,
            )
        )


@pytest.mark.parametrize(
    ("fragments", "expected"),
    [
        pytest.param(
            [
                _tool_delta(0, id="call0", function={"name": "foo", "arguments": '{"x":1}'}),
                _tool_delta(0, id="call1", function={"name": "bar", "arguments": '{"y":2}'}),
            ],
            [("call0", "foo", '{"x":1}'), ("call1", "bar", '{"y":2}')],
            id="shared-index-complete",
        ),
        pytest.param(
            [
                _tool_delta(0, id="call0", function={"name": "foo", "arguments": '{"x":'}),
                _tool_delta(0, id="call1", function={"name": "bar", "arguments": '{"y":'}),
                _tool_delta(0, id="call0", function={"arguments": "1}"}),
                _tool_delta(0, id="call1", function={"arguments": "2}"}),
            ],
            [("call0", "foo", '{"x":1}'), ("call1", "bar", '{"y":2}')],
            id="shared-index-interleaved-ids",
        ),
        pytest.param(
            [
                _tool_delta(0, id="call0", function={"name": "foo", "arguments": '{"x":'}),
                {"function": {"arguments": "1}"}},
            ],
            [("call0", "foo", '{"x":1}')],
            id="continuation-without-index",
        ),
        pytest.param(
            [
                {"id": "call0", "function": {"name": "foo", "arguments": '{"x":'}},
                _tool_delta(0, function={"arguments": "1}"}),
            ],
            [("call0", "foo", '{"x":1}')],
            id="index-arrives-late",
        ),
        pytest.param(
            [
                _tool_delta(0, id="call0", function={"name": "foo", "arguments": '{"x":'}),
                _tool_delta(0, id=None, function={"arguments": "1}"}),
            ],
            [("call0", "foo", '{"x":1}')],
            id="null-continuation-id",
        ),
        pytest.param(
            [
                _tool_delta(0, id="call0", function={"name": "foo", "arguments": '{"x":'}),
                _tool_delta(0, id="", function={"arguments": "1}"}),
            ],
            [("call0", "foo", '{"x":1}')],
            id="empty-continuation-id",
        ),
        pytest.param(
            [
                _tool_delta(0, function={"name": "foo", "arguments": '{"x":1}'}),
                _tool_delta(0, function={"name": "bar", "arguments": '{"y":2}'}),
            ],
            [(None, "foo", '{"x":1}'), (None, "bar", '{"y":2}')],
            id="shared-index-without-ids",
        ),
        pytest.param(
            [
                _tool_delta(0, id="call0", function={"name": "foo", "arguments": '{"x":'}),
                _tool_delta(0, function={"arguments": "1}"}),
                _tool_delta(0, id="call1", function={"name": "bar", "arguments": '{"y":'}),
                _tool_delta(0, function={"arguments": "2}"}),
            ],
            [("call0", "foo", '{"x":1}'), ("call1", "bar", '{"y":2}')],
            id="shared-index-sequential",
        ),
        pytest.param(
            [
                {"function": {"name": "foo", "arguments": '{"x":1}'}},
                _tool_delta(0, id="call1"),
                _tool_delta(0, function={"name": "bar", "arguments": '{"y":2}'}),
            ],
            [(None, "foo", '{"x":1}'), ("call1", "bar", '{"y":2}')],
            id="late-index-with-new-id-after-unidentified-call",
        ),
        pytest.param(
            [
                {"id": "call0", "function": {"name": "foo", "arguments": '{"x":1}'}},
                _tool_delta(0, id="call1"),
                _tool_delta(0, function={"name": "bar", "arguments": '{"y":2}'}),
            ],
            [("call0", "foo", '{"x":1}'), ("call1", "bar", '{"y":2}')],
            id="late-index-with-different-id",
        ),
    ],
)
def test_stream_tool_identity_fallbacks(fragments, expected) -> None:
    events = [
        _stream_event([fragment], "answer" if i == 0 else None)
        for i, fragment in enumerate(fragments)
    ]
    chunks = _invoke_stream(events)
    calls = [call for chunk in chunks for call in chunk.delta.message.tool_calls]
    assert len(calls) == len(expected)
    assert len({call.id for call in calls}) == len(calls)
    for call, (call_id, name, arguments) in zip(calls, expected, strict=True):
        assert call.id
        if call_id is not None:
            assert call.id == call_id
        assert (call.function.name, call.function.arguments) == (name, arguments)
    assert "".join(chunk.delta.message.content or "" for chunk in chunks) == "answer"
    assert chunks[-1].delta.finish_reason == "tool_calls"
    assert chunks[-1].delta.usage.total_tokens == 20


@pytest.mark.parametrize("indexed", [True, False], ids=["indexed", "unindexed"])
@pytest.mark.parametrize("tail_arguments", ["1}", ""], ids=["continuation", "empty-tail"])
def test_stream_repeated_id_and_name_preserve_function_name(indexed, tail_arguments) -> None:
    first_arguments = '{"x":' if tail_arguments else '{"x":1}'
    first = {"id": "call0", "function": {"name": "foo", "arguments": first_arguments}}
    tail = {"id": "call0", "function": {"name": "foo", "arguments": tail_arguments}}
    if indexed:
        first["index"] = 0
        tail["index"] = 0
    chunks = _invoke_stream([_stream_event([first], "answer"), _stream_event([tail])])
    _assert_stream_result(chunks, {"call0": ("foo", '{"x":1}')})


def test_stream_parallel_repeated_ids_and_names_preserve_function_names() -> None:
    chunks = _invoke_stream(
        [
            _stream_event(
                [
                    _tool_delta(0, id="call0", function={"name": "foo", "arguments": '{"x":'}),
                    _tool_delta(1, id="call1", function={"name": "bar", "arguments": '{"y":'}),
                ],
                "answer",
            ),
            _stream_event(
                [
                    _tool_delta(0, id="call0", function={"name": "foo", "arguments": "1}"}),
                    _tool_delta(1, id="call1", function={"name": "bar", "arguments": "2}"}),
                ]
            ),
        ]
    )
    _assert_stream_result(chunks, {"call0": ("foo", '{"x":1}'), "call1": ("bar", '{"y":2}')})
