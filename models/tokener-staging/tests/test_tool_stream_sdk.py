from pathlib import Path

import pytest
import yaml
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import AIModelEntity
from test_tool_stream import _assert_stream_result, _invoke_stream, _stream_event, _tool_delta


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
    "events",
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
            id="shared-index-id-lookup",
        ),
        pytest.param(
            [
                _stream_event([{"id": "call0", "function": {"name": "foo", "arguments": '{"x":'}}]),
                _stream_event([_tool_delta(0, function={"arguments": "1}"})]),
            ],
            id="S4-late-index",
        ),
        pytest.param(
            [
                _stream_event(
                    [_tool_delta(0, id="call0", function={"name": "foo", "arguments": '{"x":'})]
                ),
                _stream_event([{"function": {"arguments": "1}"}}]),
            ],
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
            id="G3-reasoning-resumes",
        ),
    ],
)
def test_stream_preserves_sdk_baseline_values(events) -> None:
    schema = yaml.safe_load(Path("models/llm/deepseek-v4-pro.yaml").read_text(encoding="utf-8"))
    reference = OAICompatLargeLanguageModel(model_schemas=[AIModelEntity(**schema)])
    expected = _stream_values(_invoke_stream(events, reference))
    assert expected["tools"]
    assert expected["finish"] == ["tool_calls"]
    assert expected["usage"] == [(13, 7, 20)]
    assert _stream_values(_invoke_stream(events)) == expected


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
def test_stream_late_index_for_identified_unnamed_call_matches_sdk(index) -> None:
    events = [
        _stream_event([{"id": "call0", "function": {"arguments": '{"x":'}}]),
        _stream_event([_tool_delta(index, function={"arguments": "1}"})]),
        _stream_event([{"id": "call0", "function": {"name": "foo"}}]),
    ]
    schema = yaml.safe_load(Path("models/llm/deepseek-v4-pro.yaml").read_text(encoding="utf-8"))
    reference = OAICompatLargeLanguageModel(model_schemas=[AIModelEntity(**schema)])
    expected = _stream_values(_invoke_stream(events, reference))
    assert expected["tools"] == [("call0", "foo", '{"x":1}')]
    assert _stream_values(_invoke_stream(events)) == expected


def test_stream_named_arguments_after_complete_unnamed_call_matches_sdk() -> None:
    events = [
        _stream_event([_tool_delta(0, id="call0", function={"arguments": '{"x":1}'})]),
        _stream_event([_tool_delta(0, function={"name": "bar", "arguments": '{"y":2}'})]),
        _stream_event([_tool_delta(0, id="call0", function={"name": "foo"})]),
    ]
    schema = yaml.safe_load(Path("models/llm/deepseek-v4-pro.yaml").read_text(encoding="utf-8"))
    reference = OAICompatLargeLanguageModel(model_schemas=[AIModelEntity(**schema)])
    expected = _stream_values(_invoke_stream(events, reference))
    assert expected["tools"] == [
        ("call0", "foo", '{"x":1}'),
        ("generated", "bar", '{"y":2}'),
    ]
    assert _stream_values(_invoke_stream(events)) == expected


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
    schema = yaml.safe_load(Path("models/llm/deepseek-v4-pro.yaml").read_text(encoding="utf-8"))
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
    schema = yaml.safe_load(Path("models/llm/deepseek-v4-pro.yaml").read_text(encoding="utf-8"))
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
    schema = yaml.safe_load(Path("models/llm/deepseek-v4-pro.yaml").read_text(encoding="utf-8"))
    reference = OAICompatLargeLanguageModel(model_schemas=[AIModelEntity(**schema)])
    expected = _stream_values(_invoke_stream(events, reference))
    assert expected["tools"] == [("call0", "foo", '{"x":1}')]
    assert _stream_values(_invoke_stream(events)) == expected


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
    schema = yaml.safe_load(Path("models/llm/deepseek-v4-pro.yaml").read_text(encoding="utf-8"))
    reference = OAICompatLargeLanguageModel(model_schemas=[AIModelEntity(**schema)])
    expected = _stream_values(_invoke_stream(events, reference))
    assert expected["tools"] == [("call0", "foo", arguments)]
    assert _stream_values(_invoke_stream(events)) == expected


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
    schema = yaml.safe_load(Path("models/llm/deepseek-v4-pro.yaml").read_text(encoding="utf-8"))
    reference = OAICompatLargeLanguageModel(model_schemas=[AIModelEntity(**schema)])
    expected = _stream_values(_invoke_stream(events, reference))
    assert expected["tools"] == [
        ("call0", "foo", '{"x":1}'),
        ("generated", "bar", '{"y":2}'),
    ]
    assert _stream_values(_invoke_stream(events)) == expected
