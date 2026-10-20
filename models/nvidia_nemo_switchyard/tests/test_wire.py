import httpx
import pytest
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)

from models.llm.wire import (
    UpstreamServerError,
    _chat_deltas,
    _responses_deltas,
    _sse,
    chat_body,
    responses_body,
    to_ir,
)

COMPLETED = {"type": "response.completed", "response": {}}

CALL = AssistantPromptMessage.ToolCall(
    id="c1",
    type="function",
    function=AssistantPromptMessage.ToolCall.ToolCallFunction(
        name="bash", arguments='{"command": "ls"}'
    ),
)
TOOL = PromptMessageTool(name="bash", description="Run a command", parameters={"type": "object"})
MESSAGES = [
    SystemPromptMessage(content="be brief"),
    UserPromptMessage(content="list files"),
    AssistantPromptMessage(content="<think>\nneed ls\n</think>\n", tool_calls=[CALL]),
    ToolPromptMessage(content="a.py", tool_call_id="c1"),
]


def test_to_ir_maps_roles_tool_calls_and_reasoning():
    ir = to_ir(MESSAGES)
    assert ir["instructions"] == [{"role": "system", "content": [{"type": "text", "text": "be brief"}]}]
    assistant = ir["messages"][1]["content"]
    assert assistant[0] == {"type": "reasoning", "text": "need ls", "signature": None}
    assert assistant[1] == {"type": "tool_call", "id": "c1", "name": "bash", "arguments": {"command": "ls"}}
    assert ir["messages"][2]["content"][0]["tool_call_id"] == "c1"


def test_chat_body_replays_reasoning_on_tool_call_turns():
    body = chat_body(to_ir(MESSAGES), "m", [TOOL], {"max_tokens": 10}, ["STOP"])
    assert body["messages"][0] == {"role": "system", "content": "be brief"}
    assistant = body["messages"][2]
    assert assistant["reasoning_content"] == "need ls"
    assert assistant["tool_calls"][0]["function"] == {"name": "bash", "arguments": '{"command": "ls"}'}
    assert body["messages"][3] == {"role": "tool", "tool_call_id": "c1", "content": "a.py"}
    assert body["tools"][0]["function"]["name"] == "bash"
    assert body["max_tokens"] == 10 and body["stop"] == ["STOP"]


def test_responses_body_uses_input_items():
    body = responses_body(to_ir(MESSAGES), "m", [TOOL], {"max_tokens": 10})
    assert "instructions" not in body
    assert body["input"][0] == {"role": "system", "content": "be brief"}
    assert [item.get("type", item.get("role")) for item in body["input"]] == [
        "system",
        "user",
        "function_call",
        "function_call_output",
    ]
    assert body["tools"][0] == {
        "type": "function",
        "name": "bash",
        "description": "Run a command",
        "parameters": {"type": "object"},
        "strict": False,
    }
    assert body["max_output_tokens"] == 10
    assert body["reasoning"] == {"summary": "auto"}


def test_responses_body_with_only_a_system_prompt_has_input():
    body = responses_body(to_ir([SystemPromptMessage(content="translate hello")]), "m", None, {})
    assert body["input"] == [{"role": "system", "content": "translate hello"}]


def test_chat_stream_assembles_tool_call_fragments():
    events = [
        {"choices": [{"delta": {"reasoning_content": "hmm"}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "bash", "arguments": '{"co'}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'mmand": "ls"}'}}]}, "finish_reason": "tool_calls"}]},
        {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 7}},
    ]
    deltas = list(_chat_deltas(iter(events)))
    assert deltas[0].reasoning == "hmm"
    assert deltas[1].usage == (5, 7)
    assert deltas[2].tool_calls[0].arguments == '{"command": "ls"}'
    assert deltas[3].finish_reason == "tool_calls"


def test_responses_stream_maps_events():
    events = [
        {"type": "response.output_text.delta", "delta": "hi"},
        {"type": "response.output_item.done", "item": {"type": "function_call", "call_id": "c1", "name": "bash", "arguments": "{}"}},
        {"type": "response.completed", "response": {"usage": {"input_tokens": 3, "output_tokens": 4}}},
    ]
    deltas = list(_responses_deltas(iter(events)))
    assert deltas[0].text == "hi"
    assert deltas[1].usage == (3, 4)
    assert deltas[2].tool_calls[0].name == "bash"
    assert deltas[3].finish_reason == "tool_calls"


def test_responses_stream_separates_reasoning_summary_parts():
    events = [
        {"type": "response.reasoning_summary_part.added", "summary_index": 0},
        {"type": "response.reasoning_summary_text.delta", "delta": "first"},
        {"type": "response.reasoning_summary_part.added", "summary_index": 1},
        {"type": "response.reasoning_summary_text.delta", "delta": "second"},
        {"type": "response.output_text.delta", "delta": "answer"},
        COMPLETED,
    ]
    deltas = list(_responses_deltas(iter(events)))
    assert "".join(d.reasoning for d in deltas) == "first\n\nsecond"
    assert "".join(d.text for d in deltas) == "answer"


CALL_DONE = {
    "type": "response.output_item.done",
    "item": {"type": "function_call", "call_id": "c1", "name": "bash", "arguments": "{}"},
}
CALL_FRAGMENT = {
    "choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "bash", "arguments": '{"co'}}]}}]
}


def test_chat_stream_forwards_refusal_text():
    events = [{"choices": [{"delta": {"refusal": "I can't help with that."}, "finish_reason": "stop"}]}]
    deltas = list(_chat_deltas(iter(events)))
    assert "".join(d.text for d in deltas) == "I can't help with that."


def test_chat_stream_without_finish_reason_is_an_error():
    with pytest.raises(UpstreamServerError):
        list(_chat_deltas(iter([{"choices": [{"delta": {"content": "partial"}}]}])))
    with pytest.raises(UpstreamServerError):
        list(_chat_deltas(iter([])))


def test_chat_stream_cut_off_by_length_drops_tool_calls():
    events = [CALL_FRAGMENT, {"choices": [{"delta": {}, "finish_reason": "length"}]}]
    deltas = list(_chat_deltas(iter(events)))
    assert not any(d.tool_calls for d in deltas)
    assert deltas[-1].finish_reason == "length"


def test_chat_stream_keeps_tool_calls_reported_with_stop():
    events = [CALL_FRAGMENT, {"choices": [{"delta": {}, "finish_reason": "stop"}]}]
    deltas = list(_chat_deltas(iter(events)))
    assert [c.name for d in deltas for c in d.tool_calls] == ["bash"]


def test_responses_stream_forwards_refusal_text():
    events = [{"type": "response.refusal.delta", "delta": "I can't help with that."}, COMPLETED]
    deltas = list(_responses_deltas(iter(events)))
    assert "".join(d.text for d in deltas) == "I can't help with that."


def test_responses_stream_without_terminal_event_is_an_error():
    with pytest.raises(UpstreamServerError):
        list(_responses_deltas(iter([{"type": "response.output_text.delta", "delta": "partial"}])))
    with pytest.raises(UpstreamServerError):
        list(_responses_deltas(iter([])))


def test_responses_stream_incomplete_drops_tool_calls():
    events = [CALL_DONE, {"type": "response.incomplete", "response": {}}]
    deltas = list(_responses_deltas(iter(events)))
    assert not any(d.tool_calls for d in deltas)
    assert deltas[-1].finish_reason == "length"


def test_sse_with_invalid_json_is_an_upstream_error():
    response = httpx.Response(200, content=b"data: {not json\n\n")
    with pytest.raises(UpstreamServerError):
        list(_sse(response))
