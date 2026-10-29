import json

import httpx2
import pytest
from anthropic import AnthropicVertex
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMUsage
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeError
from dify_plugin.invocations.model.llm import merge_llm_result_chunk

from models.llm import llm

MODEL = "claude-sonnet-5"
CREDENTIALS = {"vertex_project_id": "test", "vertex_location": "global"}
ARGUMENTS = ['{ "city": "Tokyo", "n": 9007199254740993 }', '{"city":"Osaka"}']


def _start():
    return {
        "type": "message_start",
        "message": {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": MODEL,
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 1},
        },
    }


def _delta(index, delta_type, **fields):
    return {
        "type": "content_block_delta",
        "index": index,
        "delta": {"type": delta_type, **fields},
    }


def _block(index, block, deltas=()):
    return [
        {"type": "content_block_start", "index": index, "content_block": block},
        *deltas,
        {"type": "content_block_stop", "index": index},
    ]


def _finish(reason="tool_use", output_tokens=7):
    return [
        {
            "type": "message_delta",
            "delta": {"stop_reason": reason, "stop_sequence": None},
            "usage": {"output_tokens": output_tokens},
        },
        {"type": "message_stop"},
    ]


def _wire(events):
    return b"".join(
        f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()
        for event in events
    )


def _real_clients(monkeypatch, bodies):
    requests = []
    clients = []

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx2.Response(
            200,
            content=bodies[len(requests) - 1],
            headers={"content-type": "text/event-stream"},
        )

    def create(**kwargs):
        client = AnthropicVertex(
            **{**kwargs, "access_token": "local-test"},
            http_client=httpx2.Client(transport=httpx2.MockTransport(handle)),
        )
        clients.append(client)
        return client

    monkeypatch.setattr(llm, "AnthropicVertex", create)
    return requests, clients


def _adapter():
    model = llm.VertexAiLargeLanguageModel([])
    model._calc_response_usage = lambda model, credentials, prompt, completion: (
        LLMUsage.empty_usage().model_copy(
            update={
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": prompt + completion,
            }
        )
    )
    return model


def _invoke(model, prompts, *, stream):
    response = model._generate_anthropic(
        MODEL,
        CREDENTIALS,
        prompts,
        {"max_tokens": 128000, "thinking": {"type": "enabled", "budget_tokens": 1024}},
        stream=stream,
    )
    if not stream:
        return response
    result = LLMResult(
        model=MODEL,
        message=AssistantPromptMessage(content=""),
        usage=LLMUsage.empty_usage(),
    )
    for chunk in response:
        merge_llm_result_chunk(
            result, LLMResultChunk.model_validate_json(chunk.model_dump_json())
        )
    return result


def _native_content():
    citation = {
        "type": "char_location",
        "cited_text": "weather",
        "document_index": 0,
        "document_title": "Forecast",
        "start_char_index": 0,
        "end_char_index": 7,
    }
    blocks = [
        {
            "type": "thinking",
            "thinking": "consider both",
            "signature": "sig-part-1-part-2",
        },
        {"type": "redacted_thinking", "data": "opaque-redacted"},
        {
            "type": "text",
            "text": "Checking weather",
            "citations": [citation],
            "native_metadata": {"phase": "commentary", "nullable": None},
        },
        {
            "type": "tool_use",
            "id": "tool_a",
            "name": "weather",
            "input": json.loads(ARGUMENTS[0]),
        },
        {
            "type": "tool_use",
            "id": "tool_b",
            "name": "weather",
            "input": json.loads(ARGUMENTS[1]),
        },
    ]
    events = [_start()]
    events += _block(
        0,
        {"type": "thinking", "thinking": "", "signature": ""},
        [
            _delta(0, "thinking_delta", thinking="consider "),
            _delta(0, "thinking_delta", thinking="both"),
            _delta(0, "signature_delta", signature="sig-part-1"),
            _delta(0, "signature_delta", signature="-part-2"),
        ],
    )
    events += _block(1, blocks[1])
    events += _block(
        2,
        {**blocks[2], "text": "", "citations": []},
        [
            _delta(2, "text_delta", text="Checking "),
            _delta(2, "text_delta", text="weather"),
            _delta(2, "citations_delta", citation=citation),
        ],
    )
    for index, arguments in enumerate(ARGUMENTS, 3):
        events += _block(
            index,
            {**blocks[index], "input": {}},
            [
                _delta(index, "input_json_delta", partial_json=arguments[:12]),
                _delta(index, "input_json_delta", partial_json=arguments[12:]),
            ],
        )
    events += _finish()
    return blocks, events


@pytest.mark.parametrize("stream", [False, True])
def test_native_blocks_and_raw_arguments_replay_after_serialization(
    monkeypatch, stream
):
    blocks, events = _native_content()
    final_events = [
        _start(),
        *_block(0, {"type": "text", "text": "done"}),
        *_finish("end_turn"),
    ]
    requests, clients = _real_clients(monkeypatch, [_wire(events), _wire(final_events)])
    try:
        prompts = [UserPromptMessage(content="Weather?")]
        result = _invoke(_adapter(), prompts, stream=stream)
        assert result.message.content == "Checking weather"
        assert [
            call.function.arguments for call in result.message.tool_calls
        ] == ARGUMENTS
        assert result.message.opaque_body == {"anthropic_content": blocks}
        assert result.usage.total_tokens == 17
        saved = LLMResult.model_validate_json(result.model_dump_json())
        before = saved.model_dump_json()
        prompts += [saved.message] + [
            ToolPromptMessage(
                tool_call_id=call.id, name=call.function.name, content=city
            )
            for call, city in zip(
                saved.message.tool_calls, ("Tokyo result", "Osaka result")
            )
        ]
        assert _invoke(_adapter(), prompts, stream=stream).message.content == "done"
        assert requests[1]["messages"][1] == {"role": "assistant", "content": blocks}
        assert [
            block["tool_use_id"] for block in requests[1]["messages"][2]["content"]
        ] == ["tool_a", "tool_b"]
        assert requests[1]["thinking"] == {"type": "enabled", "budget_tokens": 1024}
        assert saved.model_dump_json() == before
        converted = _adapter()._convert_claude_prompt_message_to_dict(saved.message)
        converted["content"][0]["signature"] = "changed"
        assert saved.model_dump_json() == before
    finally:
        for client in clients:
            client.close()


@pytest.mark.parametrize("stream", [False, True])
def test_opaque_only_assistant_turn_is_replayed(monkeypatch, stream):
    block = {"type": "thinking", "thinking": "", "signature": "signed-omitted-thinking"}
    events = [_start(), *_block(0, block), *_finish("end_turn")]
    requests, clients = _real_clients(monkeypatch, [_wire(events), _wire(events)])
    try:
        result = _invoke(
            _adapter(), [UserPromptMessage(content="Think")], stream=stream
        )
        saved = AssistantPromptMessage.model_validate_json(
            result.message.model_dump_json()
        )
        assert saved.content == "" and saved.tool_calls == []
        _invoke(
            _adapter(),
            [
                UserPromptMessage(content="Think"),
                saved,
                UserPromptMessage(content="Continue"),
            ],
            stream=stream,
        )
        assert requests[1]["messages"][1] == {"role": "assistant", "content": [block]}
    finally:
        for client in clients:
            client.close()


def _tool_events(
    arguments="{}", *, name="weather", call_id="tool_a", finish="tool_use"
):
    block = {"type": "tool_use", "name": name, "input": {}}
    if call_id is not None:
        block["id"] = call_id
    deltas = (
        []
        if arguments is None
        else [_delta(0, "input_json_delta", partial_json=arguments)]
    )
    return [_start(), *_block(0, block, deltas), *_finish(finish)]


def _invalid_events(case):
    events = _tool_events()
    if case == "eof-partial":
        return _tool_events('{"city":')[:3]
    if case == "eof-before-stop":
        return events[:-1]
    if case == "eof-before-finish":
        return events[:-2]
    if case == "missing-block-stop":
        return [event for event in events if event["type"] != "content_block_stop"]
    if case == "error-after-stop":
        return events + [
            {
                "type": "error",
                "error": {"type": "overloaded_error", "message": "overloaded"},
            }
        ]
    if case.startswith("reason:"):
        return _tool_events(finish=case.removeprefix("reason:"))
    if case.startswith("arguments:"):
        return _tool_events(case.removeprefix("arguments:"))
    if case == "empty-name":
        return _tool_events(name="")
    if case.startswith("initial-input:"):
        events = _tool_events(None)
        events[1]["content_block"]["input"] = json.loads(
            case.removeprefix("initial-input:")
        )
        return events
    if case == "duplicate-id":
        return (
            events[:-2]
            + _block(
                1, {"type": "tool_use", "id": "tool_a", "name": "weather", "input": {}}
            )
            + _finish()
        )
    raise AssertionError(case)


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "case",
    [
        "eof-partial",
        "eof-before-stop",
        "eof-before-finish",
        "missing-block-stop",
        "error-after-stop",
        "reason:max_tokens",
        "reason:pause_turn",
        "reason:refusal",
        "reason:model_context_window_exceeded",
        "reason:end_turn",
        "reason:stop_sequence",
        "arguments:",
        'arguments:{"city":',
        "arguments:[]",
        "arguments:null",
        "initial-input:[]",
        "initial-input:null",
        "empty-name",
        "duplicate-id",
    ],
)
def test_native_sse_never_emits_calls_from_invalid_responses(monkeypatch, stream, case):
    _, clients = _real_clients(monkeypatch, [_wire(_invalid_events(case))])
    emitted = []
    try:
        with pytest.raises(InvokeError):
            response = _adapter()._generate_anthropic(
                MODEL,
                CREDENTIALS,
                [UserPromptMessage(content="Weather?")],
                {"max_tokens": 128000},
                stream=stream,
            )
            if stream:
                for chunk in response:
                    emitted.extend(chunk.delta.message.tool_calls)
            else:
                emitted.extend(response.message.tool_calls)
        assert emitted == []
    finally:
        for client in clients:
            client.close()


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("call_id", [None, ""])
def test_native_zero_argument_calls_get_unique_missing_ids_and_keep_zero_usage(
    monkeypatch, stream, call_id
):
    events = _tool_events(None, call_id=call_id)[:-2]
    block = {"type": "tool_use", "name": "weather", "input": {}}
    if call_id is not None:
        block["id"] = call_id
    events += _block(1, block)
    events += _finish(output_tokens=7)[:-1] + _finish(reason=None, output_tokens=0)
    _, clients = _real_clients(monkeypatch, [_wire(events)])
    try:
        result = _invoke(_adapter(), [UserPromptMessage(content="Ping")], stream=stream)
        calls = result.message.tool_calls
        assert len(calls) == len({call.id for call in calls}) == 2
        assert all(call.id for call in calls)
        assert [call.function.arguments for call in calls] == ["{}", "{}"]
        assert [
            block["id"] for block in result.message.opaque_body["anthropic_content"]
        ] == [call.id for call in calls]
        assert result.usage.completion_tokens == 0
    finally:
        for client in clients:
            client.close()


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("outcome", ["success", "parse-error", "invalid-block"])
def test_native_response_closes_when_iteration_stops(monkeypatch, stream, outcome):
    class Body(httpx2.SyncByteStream):
        closed = False

        def __iter__(self):
            yield from wire_parts

        def close(self):
            self.closed = True

    events = _tool_events(None)
    if outcome == "invalid-block":
        events[1]["index"] = 3
    wire_parts = [_wire([event]) for event in events]
    if outcome == "parse-error":
        wire_parts[1] = b"event: content_block_start\ndata: {\n\n"
    body = Body()
    http_client = httpx2.Client(
        transport=httpx2.MockTransport(
            lambda request: httpx2.Response(
                200, stream=body, headers={"content-type": "text/event-stream"}
            )
        )
    )
    client = AnthropicVertex(
        region="global",
        project_id="test",
        access_token="local-test",
        http_client=http_client,
    )
    monkeypatch.setattr(llm, "AnthropicVertex", lambda **kwargs: client)
    try:
        if outcome == "success":
            _invoke(_adapter(), [UserPromptMessage(content="Ping")], stream=stream)
        else:
            # Retain the traceback so garbage collection cannot hide an unclosed response.
            with pytest.raises(InvokeError) as error:
                _invoke(_adapter(), [UserPromptMessage(content="Ping")], stream=stream)
            assert error.value is not None
        assert body.closed
    finally:
        client.close()
