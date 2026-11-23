from test_tool_stream import _invoke_stream, _stream_event, _tool_delta


def test_stream_new_arguments_after_a_complete_idless_call_keep_calls_separate() -> None:
    chunks = _invoke_stream(
        [
            _stream_event([_tool_delta(0, function={"name": "foo", "arguments": '{"x":1}'})]),
            _stream_event([_tool_delta(0, id="call1", function={"arguments": '{"y":2}'})]),
            _stream_event([_tool_delta(0, function={"name": "bar"})]),
        ]
    )
    calls = [call for chunk in chunks for call in chunk.delta.message.tool_calls or []]
    assert [(call.function.name, call.function.arguments) for call in calls] == [
        ("foo", '{"x":1}'),
        ("bar", '{"y":2}'),
    ]
    assert all(call.id for call in calls)
    assert len({call.id for call in calls}) == 2
