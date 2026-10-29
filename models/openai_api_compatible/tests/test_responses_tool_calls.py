from types import SimpleNamespace

from dify_plugin.entities.model.llm import LLMUsage

from models.llm.llm import OpenAILargeLanguageModel


def _model():
    model = OpenAILargeLanguageModel([])
    model._calc_response_usage = lambda name, credentials, prompt, completion: (
        LLMUsage.empty_usage().model_copy(
            update={
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": prompt + completion,
            }
        )
    )
    return model


def _item(call_id, arguments):
    return SimpleNamespace(
        type="function_call",
        id="item_" + call_id,
        call_id=call_id,
        name="weather",
        arguments=arguments,
    )


def test_interleaved_response_calls_emit_final_arguments_once():
    model = _model()
    arguments = ['{ "city": "Paris", "n": 9007199254740993 }', '{"city":"Tokyo"}']
    calls = [_item("a", arguments[0]), _item("b", arguments[1])]
    events = [
        SimpleNamespace(type="response.output_item.added", item=_item("a", "")),
        SimpleNamespace(type="response.output_item.added", item=_item("b", "")),
        SimpleNamespace(
            type="response.function_call_arguments.delta",
            item_id="item_a",
            delta=arguments[0][:10],
        ),
        SimpleNamespace(
            type="response.function_call_arguments.delta",
            item_id="item_b",
            delta=arguments[1],
        ),
        SimpleNamespace(
            type="response.function_call_arguments.delta",
            item_id="item_a",
            delta=arguments[0][10:],
        ),
        SimpleNamespace(type="response.output_item.done", item=calls[0]),
        SimpleNamespace(type="response.output_item.done", item=calls[1]),
        SimpleNamespace(
            type="response.completed",
            response=SimpleNamespace(
                usage=SimpleNamespace(input_tokens=10, output_tokens=3)
            ),
        ),
    ]

    chunks = list(model._handle_responses_stream_response("test", {}, iter(events), []))
    emitted = [call for chunk in chunks for call in chunk.delta.message.tool_calls]
    assert [call.id for call in emitted] == ["a", "b"]
    assert [call.function.arguments for call in emitted] == arguments
    assert [
        chunk.delta.usage.total_tokens
        for chunk in chunks
        if chunk.delta.usage is not None
    ] == [13]


def test_calls_without_provider_ids_get_independent_ids():
    model = _model()
    items = [
        SimpleNamespace(type="function_call", name="weather", arguments="{}")
        for _ in range(2)
    ]
    response = SimpleNamespace(
        output=items, usage=SimpleNamespace(input_tokens=10, output_tokens=3)
    )
    result = model._handle_responses_response("test", {}, response, [])
    assert len({call.id for call in result.message.tool_calls}) == 2
    assert all(call.id for call in result.message.tool_calls)

    events = [
        SimpleNamespace(type="response.output_item.done", item=item) for item in items
    ]
    events.append(SimpleNamespace(type="response.completed", response=response))
    chunks = list(model._handle_responses_stream_response("test", {}, iter(events), []))
    calls = [call for chunk in chunks for call in chunk.delta.message.tool_calls]
    assert len({call.id for call in calls}) == 2
    assert all(call.id for call in calls)
