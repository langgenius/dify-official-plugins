from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)

from models.llm.wire import (
    _chat_deltas,
    _responses_deltas,
    chat_body,
    responses_body,
    to_ir,
)

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
    assert body["instructions"] == "be brief"
    assert [item.get("type", item.get("role")) for item in body["input"]] == [
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
