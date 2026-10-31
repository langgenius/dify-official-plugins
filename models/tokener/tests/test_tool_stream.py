import json
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
import yaml
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import PromptMessageTool, UserPromptMessage
from dify_plugin.errors.model import InvokeError

from models._credentials import ENDPOINT_URL
from models.llm.llm import TokenerLargeLanguageModel

MODEL = "gpt-5.6-sol"


def _model() -> TokenerLargeLanguageModel:
    schema = yaml.safe_load(Path("models/llm/gpt-5.6-sol.yaml").read_text(encoding="utf-8"))
    return TokenerLargeLanguageModel(model_schemas=[AIModelEntity(**schema)])


def _stream_response(events: list[dict]) -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response.encoding = "utf-8"
    response._content = "\n\n".join(
        [
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
    ).encode()
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
                {"max_tokens": 32},
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
                {"max_tokens": 32},
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
    assert chunks[-1].delta.message.tool_calls[0].id == "call0"
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


@pytest.mark.parametrize("ending", [b"data: not-json\n\n", b""])
def test_stream_invalid_or_missing_termination_rejects_the_result(ending) -> None:
    response = _stream_response([])
    response._content = (
        b': keepalive\n\ndata: {"choices": [{"delta": {"content": "answer", "tool_calls": '
        b'[{"index": 0, "id": "call0", "function": {"name": "foo", "arguments": "{}"}}]}}]}\n\n'
        + ending
    )
    chunks = []
    with patch("requests.post", return_value=response):
        with pytest.raises(InvokeError):
            chunks.extend(
                _model().invoke(
                    MODEL,
                    {"api_key": "test-key"},
                    [UserPromptMessage(content="Run tools")],
                    {},
                    stream=True,
                )
            )
    assert "".join(chunk.delta.message.get_text_content() for chunk in chunks) == "answer"
    assert all(chunk.delta.usage is None for chunk in chunks)
    assert not any(chunk.delta.message.tool_calls for chunk in chunks)


def test_stream_upstream_error_is_propagated() -> None:
    response = _stream_response([])
    response._content = b'data: {"error": "upstream rejected request"}\n\n'
    with (
        patch("requests.post", return_value=response),
        pytest.raises(InvokeError, match="upstream"),
    ):
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


def _stream_values(chunks: list) -> dict:
    return {
        "tools": [
            (
                "generated" if call.id.startswith("chatcmpl-tool-") else call.id,
                call.function.name,
                call.function.arguments,
            )
            for chunk in chunks
            for call in chunk.delta.message.tool_calls
        ],
        "content": "".join(chunk.delta.message.content or "" for chunk in chunks),
        "finish": [chunk.delta.finish_reason for chunk in chunks if chunk.delta.finish_reason],
        "usage": [
            (
                chunk.delta.usage.prompt_tokens,
                chunk.delta.usage.completion_tokens,
                chunk.delta.usage.total_tokens,
            )
            for chunk in chunks
            if chunk.delta.usage is not None
        ],
    }


@pytest.mark.parametrize("indexed", [True, False], ids=["A5-P20", "A6-P21"])
@pytest.mark.parametrize("second_name", ["bar", "foo"], ids=["different-name", "same-name"])
def test_stream_new_id_and_name_start_a_call_after_an_idless_call(indexed, second_name) -> None:
    first = {"function": {"name": "foo", "arguments": '{"x":1}'}}
    second = {"id": "call1", "function": {"name": second_name, "arguments": '{"y":2}'}}
    if indexed:
        first["index"] = second["index"] = 0
    events = [_stream_event([first]), _stream_event([second])]
    values = _stream_values(_invoke_stream(events))
    assert values["tools"] == [("generated", "foo", '{"x":1}'), ("call1", second_name, '{"y":2}')]


@pytest.mark.parametrize(
    ("events", "expected_tools", "expected_content"),
    [
        pytest.param(
            [
                _stream_event(
                    [_tool_delta(0, id="call0", function={"name": "foo", "arguments": '{"x":'})]
                ),
                _stream_event(
                    [_tool_delta(0, id="call0", function={"name": "foo", "arguments": "1}"})]
                ),
            ],
            [("call0", "foo", '{"x":1}')],
            "",
            id="repeated-id-name",
        ),
        pytest.param(
            [
                _stream_event(
                    [_tool_delta(0, id="call0", function={"name": "foo", "arguments": '{"x":'})]
                ),
                _stream_event(
                    [_tool_delta(0, id="call1", function={"name": "bar", "arguments": '{"y":'})]
                ),
                _stream_event([_tool_delta(0, id="call0", function={"arguments": "1}"})]),
                _stream_event([_tool_delta(0, id="call1", function={"arguments": "2}"})]),
            ],
            [("call0", "foo", '{"x":1}'), ("call1", "bar", '{"y":2}')],
            "",
            id="shared-index-id-lookup",
        ),
        pytest.param(
            [
                _stream_event([{"id": "call0", "function": {"name": "foo", "arguments": '{"x":'}}]),
                _stream_event([_tool_delta(0, function={"arguments": "1}"})]),
            ],
            [("call0", "foo", '{"x":1}')],
            "",
            id="S4-late-index",
        ),
        pytest.param(
            [
                _stream_event(
                    [_tool_delta(0, id="call0", function={"name": "foo", "arguments": '{"x":'})]
                ),
                _stream_event([{"function": {"arguments": "1}"}}]),
            ],
            [("call0", "foo", '{"x":1}')],
            "",
            id="unindexed-continuation",
        ),
        *[
            pytest.param(
                [
                    _stream_event(
                        [
                            {
                                "function": {"name": "foo", "arguments": '{"x":1}'},
                                **({"index": 0} if indexed else {}),
                            }
                        ]
                    ),
                    _stream_event(
                        [
                            {
                                "id": "call1",
                                "function": {"name": name, "arguments": '{"y":2}'},
                                **({"index": 0} if indexed else {}),
                            }
                        ]
                    ),
                ],
                [("generated", "foo", '{"x":1}'), ("call1", name, '{"y":2}')],
                "",
                id=f"new-id-after-idless-{indexed}-{name}",
            )
            for indexed in (True, False)
            for name in ("foo", "bar")
        ],
        pytest.param(
            [
                {"choices": [{"delta": {"reasoning_content": "a"}}]},
                {
                    "choices": [
                        {
                            "delta": {
                                "reasoning_content": "b",
                                "tool_calls": [
                                    _tool_delta(
                                        0, id="call0", function={"name": "foo", "arguments": "{}"}
                                    )
                                ],
                            }
                        }
                    ]
                },
                {"choices": [{"delta": {"reasoning_content": "c"}}]},
                {"choices": [{"delta": {"content": "ans"}}]},
            ],
            [("call0", "foo", "{}")],
            "<think>\nab\n</think><think>\nc\n</think>ans",
            id="G3-reasoning-resumes",
        ),
    ],
)
def test_stream_preserves_tool_values(events, expected_tools, expected_content) -> None:
    assert _stream_values(_invoke_stream(events)) == {
        "tools": expected_tools,
        "content": expected_content,
        "finish": ["tool_calls"],
        "usage": [(13, 7, 20)],
    }


def test_missing_usage_counts_tool_definitions_and_collected_arguments() -> None:
    arguments = json.dumps({"query": "word " * 100})
    response = _stream_response([])
    response._content = (
        "data: "
        + json.dumps(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call0",
                                    "function": {"name": "foo", "arguments": arguments},
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        )
        + "\n\ndata: [DONE]\n\n"
    ).encode()
    tool = PromptMessageTool(
        name="foo", description="long schema " * 20, parameters={"type": "object"}
    )
    with patch("requests.post", return_value=response):
        chunks = list(
            _model().invoke(
                MODEL,
                {"api_key": "test-key"},
                [UserPromptMessage(content="Use foo")],
                tools=[tool],
                stream=True,
            )
        )

    usage = chunks[-1].delta.usage
    assert usage.prompt_tokens >= 40
    assert usage.completion_tokens >= 100
    assert chunks[-1].delta.message.tool_calls[0].function.arguments == arguments
    assert sum(bool(chunk.delta.message.tool_calls) for chunk in chunks) == 1


def test_stream_new_arguments_after_a_complete_idless_call_keep_calls_separate() -> None:
    chunks = _invoke_stream(
        [
            _stream_event([_tool_delta(0, function={"name": "foo", "arguments": '{"x":1}'})]),
            _stream_event([_tool_delta(0, id="call1", function={"arguments": '{"y":2}'})]),
            _stream_event([_tool_delta(0, function={"name": "bar"})]),
        ]
    )
    assert _stream_values(chunks)["tools"] == [
        ("generated", "foo", '{"x":1}'),
        ("call1", "bar", '{"y":2}'),
    ]


@pytest.mark.parametrize(
    "identity",
    [
        pytest.param({"index": 0, "id": "call1"}, id="B06-id-only"),
        pytest.param(
            {"index": 0, "id": "call1", "function": {"arguments": ""}},
            id="B07-empty-arguments",
        ),
        pytest.param({"id": "call1"}, id="B08-unindexed-id-only"),
    ],
)
def test_stream_new_id_after_complete_idless_call_does_not_replace_the_call(identity) -> None:
    index = {"index": 0} if "index" in identity else {}
    events = [
        _stream_event([{**index, "function": {"name": "foo", "arguments": '{"x":1}'}}]),
        _stream_event([identity]),
        _stream_event(
            [{**index, "id": "call1", "function": {"name": "bar", "arguments": '{"y":2}'}}]
        ),
    ]
    values = _stream_values(_invoke_stream(events))
    assert values["tools"] == [
        ("generated", "foo", '{"x":1}'),
        ("call1", "bar", '{"y":2}'),
    ]
    assert values["finish"] == ["tool_calls"]
    assert values["usage"] == [(13, 7, 20)]


@pytest.mark.parametrize(
    "fragment",
    [
        pytest.param({"index": 1}, id="B14-without-function"),
        pytest.param({"index": 1, "function": {}}, id="B15-empty-function"),
        pytest.param({"index": 1, "type": "function"}, id="B16-type-only"),
    ],
)
def test_stream_stray_index_without_function_values_does_not_emit_an_empty_call(fragment) -> None:
    chunks = _invoke_stream(
        [
            _stream_event(
                [_tool_delta(0, id="call0", function={"name": "foo", "arguments": '{"x":1}'})],
                "answer",
            ),
            _stream_event([fragment]),
        ]
    )
    _assert_stream_result(chunks, {"call0": ("foo", '{"x":1}')})


@pytest.mark.parametrize("index", [0, 1])
def test_stream_late_index_for_identified_unnamed_call_keeps_tool_values(index) -> None:
    events = [
        _stream_event([{"id": "call0", "function": {"arguments": '{"x":'}}]),
        _stream_event([_tool_delta(index, function={"arguments": "1}"})]),
        _stream_event([{"id": "call0", "function": {"name": "foo"}}]),
    ]
    values = _stream_values(_invoke_stream(events))
    assert values["tools"] == [("call0", "foo", '{"x":1}')]
    assert values["finish"] == ["tool_calls"]
    assert values["usage"] == [(13, 7, 20)]


def test_stream_named_arguments_after_complete_unnamed_call_matches_sdk() -> None:
    events = [
        _stream_event([_tool_delta(0, id="call0", function={"arguments": '{"x":1}'})]),
        _stream_event([_tool_delta(0, function={"name": "bar", "arguments": '{"y":2}'})]),
        _stream_event([_tool_delta(0, id="call0", function={"name": "foo"})]),
    ]
    values = _stream_values(_invoke_stream(events))
    assert values["tools"] == [
        ("call0", "foo", '{"x":1}'),
        ("generated", "bar", '{"y":2}'),
    ]
    assert values["finish"] == ["tool_calls"]
    assert values["usage"] == [(13, 7, 20)]


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="An unnamed call with empty arguments is ambiguous with a late function name.",
)
def test_stream_known_ambiguity_for_empty_unnamed_call_with_late_name() -> None:
    events = [
        _stream_event([{"id": "call0", "function": {"arguments": ""}}]),
        _stream_event([{"function": {"name": "bar", "arguments": '{"y":2}'}}]),
        _stream_event([{"id": "call0", "function": {"name": "foo"}}]),
    ]
    schema = yaml.safe_load(Path("models/llm/gpt-5.6-sol.yaml").read_text(encoding="utf-8"))
    reference = OAICompatLargeLanguageModel(model_schemas=[AIModelEntity(**schema)])
    expected = _stream_values(_invoke_stream(events, reference))
    assert expected["tools"]
    assert _stream_values(_invoke_stream(events)) == expected


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="Unindexed interleaving is ambiguous with a late name and nested argument continuation.",
)
def test_stream_known_ambiguity_for_unindexed_interleaved_unnamed_calls() -> None:
    events = [
        _stream_event(
            [{"id": "call0", "type": "function", "function": {"arguments": '{"x":'}}],
            content="answer",
        ),
        _stream_event([{"type": "function", "function": {"name": "bar", "arguments": '{"y":'}}]),
        _stream_event([{"id": "call0", "function": {"name": "foo", "arguments": "1}"}}]),
        _stream_event([{"function": {"arguments": "2}"}}]),
    ]
    schema = yaml.safe_load(Path("models/llm/gpt-5.6-sol.yaml").read_text(encoding="utf-8"))
    reference = OAICompatLargeLanguageModel(model_schemas=[AIModelEntity(**schema)])
    expected = _stream_values(_invoke_stream(events, reference))
    assert expected["tools"] == [
        ("call0", "foo", '{"x":1}'),
        ("generated", "bar", '{"y":2}'),
    ]
    assert _stream_values(_invoke_stream(events)) == expected


@pytest.mark.parametrize(
    "fragment",
    [
        {"index": 0, "type": "custom"},
        {"index": 0, "type": "custom", "function": {}},
        {"type": "custom"},
    ],
)
def test_stream_type_without_function_does_not_replace_existing_call_type(fragment) -> None:
    events = [
        _stream_event(
            [
                _tool_delta(
                    0, id="call0", type="function", function={"name": "foo", "arguments": '{"x":1}'}
                )
            ]
        ),
        _stream_event([fragment]),
    ]
    calls = [
        call for chunk in _invoke_stream(events) for call in chunk.delta.message.tool_calls or []
    ]
    assert [
        (call.id, call.type, call.function.name, call.function.arguments) for call in calls
    ] == [("call0", "function", "foo", '{"x":1}')]


def test_stream_unbound_index_continuation_of_identified_unnamed_call_matches_sdk() -> None:
    events = [
        _stream_event([_tool_delta(0, id="call0", function={"arguments": '{"x":'})]),
        _stream_event([_tool_delta(1, function={"arguments": "1}"})]),
        _stream_event([_tool_delta(0, id="call0", function={"name": "foo"})]),
    ]
    values = _stream_values(_invoke_stream(events))
    assert values["tools"] == [("call0", "foo", '{"x":1}')]
    assert values["finish"] == ["tool_calls"]
    assert values["usage"] == [(13, 7, 20)]


@pytest.mark.parametrize("dialect", ["indexed", "late-index"])
def test_stream_whitespace_continuation_with_unbound_index_matches_sdk(dialect) -> None:
    if dialect == "indexed":
        events = [
            _stream_event(
                [_tool_delta(0, id="call0", function={"name": "foo", "arguments": '{"x":1}'})]
            ),
            _stream_event([_tool_delta(1, function={"arguments": "\n"})]),
        ]
        arguments = '{"x":1}\n'
    else:
        events = [
            _stream_event([{"id": "call0", "function": {"arguments": '{"x":1}'}}]),
            _stream_event([_tool_delta(0, function={"arguments": " "})]),
            _stream_event([{"id": "call0", "function": {"name": "foo"}}]),
        ]
        arguments = '{"x":1} '
    values = _stream_values(_invoke_stream(events))
    assert values["tools"] == [("call0", "foo", arguments)]
    assert values["finish"] == ["tool_calls"]
    assert values["usage"] == [(13, 7, 20)]


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="A name-only fragment can be a late name after complete arguments.",
)
def test_stream_known_ambiguity_for_complete_unnamed_call_with_name_only_fragment() -> None:
    events = [
        _stream_event([{"id": "call0", "function": {"arguments": '{"x":1}'}}]),
        _stream_event([{"function": {"name": "bar"}}]),
        _stream_event([{"function": {"arguments": '{"y":2}'}}]),
        _stream_event([{"id": "call0", "function": {"name": "foo"}}]),
    ]
    schema = yaml.safe_load(Path("models/llm/gpt-5.6-sol.yaml").read_text(encoding="utf-8"))
    reference = OAICompatLargeLanguageModel(model_schemas=[AIModelEntity(**schema)])
    expected = _stream_values(_invoke_stream(events, reference))
    assert expected["tools"] == [
        ("call0", "foo", '{"x":1}'),
        ("generated", "bar", '{"y":2}'),
    ]
    assert _stream_values(_invoke_stream(events)) == expected
