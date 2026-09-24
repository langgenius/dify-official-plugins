import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
import yaml
from anthropic.types import (
    ContentBlockDeltaEvent,
    ContentBlockStartEvent,
    ContentBlockStopEvent,
    Message,
    MessageDeltaEvent,
    MessageStartEvent,
    MessageStopEvent,
)
from dify_plugin.core.runtime import Session
from dify_plugin.core.server.stdio.request_reader import StdioRequestReader
from dify_plugin.core.server.stdio.response_writer import StdioResponseWriter
from dify_plugin.entities.model import AIModelEntity, ModelFeature
from dify_plugin.entities.model.llm import LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    UserPromptMessage,
    ensure_prompt_message,
)
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError
from dify_plugin.file.file import File, FileType
from dify_plugin.interfaces.agent import AgentModelConfig, ToolEntity
from models.llm.llm import AnthropicLargeLanguageModel


def _stream(response, truncated=False):
    yield MessageStartEvent(
        type="message_start", message=response.model_copy(update={"content": []})
    )
    for index, block in enumerate(response.content):
        start = block.model_dump(mode="json", exclude_none=True)
        deltas = []
        if block.type == "thinking":
            start.update(thinking="", signature="")
            deltas = [
                {"type": "thinking_delta", "thinking": block.thinking},
                {"type": "signature_delta", "signature": block.signature},
            ]
        elif block.type == "text":
            start["text"] = ""
            deltas = [{"type": "text_delta", "text": block.text}]
        elif block.type == "tool_use":
            start["input"] = {}
            arguments = json.dumps(block.input)
            if truncated:
                arguments = arguments[:5]
            deltas = [
                {"type": "input_json_delta", "partial_json": arguments[:5]},
                {"type": "input_json_delta", "partial_json": arguments[5:]},
            ]
        yield ContentBlockStartEvent(
            type="content_block_start", index=index, content_block=start
        )
        for delta in deltas:
            yield ContentBlockDeltaEvent(
                type="content_block_delta", index=index, delta=delta
            )
        yield ContentBlockStopEvent(type="content_block_stop", index=index)
    yield MessageDeltaEvent(
        type="message_delta",
        delta={
            "stop_reason": "max_tokens" if truncated else "tool_use",
            "stop_sequence": None,
        },
        usage={"output_tokens": 10},
    )
    yield MessageStopEvent(type="message_stop")


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("with_image", [False, True])
def test_agent_replays_each_assistants_original_signed_content(
    stream, with_image, monkeypatch
):
    monkeypatch.syspath_prepend(
        str(Path(__file__).parents[3] / "agent-strategies/cot_agent")
    )
    from strategies.function_calling import FunctionCallingAgentStrategy

    schema = yaml.safe_load(
        (Path(__file__).parents[1] / "models/llm/claude-opus-5-5.yaml").read_text()
    )
    entity = AIModelEntity.model_validate(schema)
    if not stream:
        entity.features.remove(ModelFeature.STREAM_TOOL_CALL)
    responses = []
    expected = []
    for turn in range(2):
        response = Message(
            id=f"msg_{turn}",
            type="message",
            role="assistant",
            model="claude-opus-5-5",
            stop_reason="tool_use",
            usage={"input_tokens": 20, "output_tokens": 10},
            content=[
                {"type": "thinking", "thinking": "", "signature": f"omitted_{turn}"},
                {"type": "text", "text": f"Checking {turn}"},
                {
                    "type": "tool_use",
                    "id": f"tool_{turn}_a",
                    "name": "lookup",
                    "input": {"q": "a"},
                },
                {"type": "redacted_thinking", "data": f"encrypted_{turn}"},
                {
                    "type": "thinking",
                    "thinking": "Next check",
                    "signature": f"progress_{turn}",
                },
                {
                    "type": "tool_use",
                    "id": f"tool_{turn}_b",
                    "name": "lookup",
                    "input": {"q": "b"},
                },
            ],
        )
        responses.append(response)
        expected.append(
            [
                block.model_dump(mode="json", exclude_none=True)
                for block in response.content
            ]
        )

    responses.append(
        Message(
            id="done",
            type="message",
            role="assistant",
            model="claude-opus-5-5",
            stop_reason="end_turn",
            usage={"input_tokens": 20, "output_tokens": 10},
            content=[{"type": "text", "text": "Done"}],
        )
    )
    histories = []
    requests = []
    tool_definitions = []

    def respond(request):
        invocation = json.loads(request.content)["data"]["data"]
        payload = invocation["request"]
        assert payload["stream"] is stream
        history = [
            ensure_prompt_message(message) for message in payload["prompt_messages"]
        ]
        tool_definitions.append(payload["tools"])
        llm = AnthropicLargeLanguageModel(model_schemas=[entity])
        _, messages = llm._convert_prompt_messages(history)
        histories.append(history)
        requests.append(messages)
        response = responses[len(requests) - 1]
        if stream:
            chunks = list(
                llm._handle_chat_generate_stream_response(
                    response.model, {}, _stream(response), history
                )
            )
            # A later chunk without metadata must not erase the signed content.
            chunks.append(
                LLMResultChunk(
                    model=response.model,
                    delta=LLMResultChunkDelta(
                        index=len(chunks),
                        message=AssistantPromptMessage(content=""),
                    ),
                )
            )
        else:
            result = llm._handle_chat_generate_response(
                response.model, {}, response, history
            )
            chunks = [
                LLMResultChunk(
                    model=result.model,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=result.message,
                        usage=result.usage,
                    ),
                )
            ]
        events = [
            {
                "session_id": "replay",
                "event": "backwards_response",
                "data": {
                    "backwards_request_id": invocation["backwards_request_id"],
                    "event": "response",
                    "message": "",
                    "data": chunk.model_dump(mode="json"),
                },
            }
            for chunk in chunks
        ]
        return httpx.Response(200, text="\n".join(map(json.dumps, events)))

    client_type = httpx.Client
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        "dify_plugin.core.runtime.httpx.Client",
        lambda: client_type(transport=transport),
    )
    tool = ToolEntity.model_validate(
        {
            "identity": {
                "author": "test",
                "name": "lookup",
                "label": {"en_US": "lookup"},
                "provider": "test",
            },
            "provider_type": "mcp",
            "runtime_parameters": {},
            "parameters": [
                {
                    "name": "q",
                    "type": "string",
                    "form": "llm",
                    "label": {"en_US": "Query"},
                    "human_description": {"en_US": "Query to look up"},
                    "llm_description": "Query to look up",
                    "input_schema": {"type": "string", "enum": ["a", "b"]},
                }
            ],
        }
    )

    def invoke_tool(**kwargs):
        tool.parameters[0].llm_description = "Changed after execution"
        tool.parameters[0].input_schema["enum"].append("changed")
        return iter(
            [
                ToolInvokeMessage(
                    type=ToolInvokeMessage.MessageType.TEXT,
                    message=ToolInvokeMessage.TextMessage(text="Found"),
                )
            ]
        )

    image = File(
        url="https://example.invalid/image.png",
        mime_type="image/png",
        filename="image.png",
        extension=".png",
        size=3,
        type=FileType.IMAGE,
    )
    image._blob = b"png"
    model = AgentModelConfig(
        provider="anthropic",
        model="claude-opus-5-5",
        mode="chat",
        entity=entity,
        history_prompt_messages=[
            UserPromptMessage(content="First question"),
            AssistantPromptMessage(content="Earlier ordinary answer"),
        ],
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        session = Session(
            session_id="replay",
            executor=executor,
            reader=StdioRequestReader(),
            writer=StdioResponseWriter(),
            dify_plugin_daemon_url="http://daemon.test",
        )
        session.tool.invoke = Mock(side_effect=invoke_tool)
        strategy = FunctionCallingAgentStrategy(runtime=Mock(), session=session)
        list(
            strategy._invoke(
                {
                    "query": "Second question",
                    "instruction": "Use lookup",
                    "files": [image] if with_image else [],
                    "model": model,
                    "tools": [tool],
                    "maximum_iterations": 3,
                }
            )
        )

    assert len(requests) == 3
    assert session.tool.invoke.call_count == 4
    assert len(model.history_prompt_messages) == 2
    assert all(definitions == tool_definitions[0] for definitions in tool_definitions)
    for turn, messages in enumerate(requests):
        assert messages[:3] == requests[0][:3]
        assistants = [
            message["content"] for message in messages if message["role"] == "assistant"
        ]
        assert assistants == [
            [{"type": "text", "text": "Earlier ordinary answer"}],
            *expected[:turn],
        ]
    assistants[-1][0]["signature"] = "changed"
    _, messages = AnthropicLargeLanguageModel()._convert_prompt_messages(histories[-1])
    assert [
        message["content"] for message in messages if message["role"] == "assistant"
    ][1:] == expected


def test_truncated_tool_arguments_raise_an_actionable_invoke_error():
    response = Message(
        id="truncated",
        type="message",
        role="assistant",
        model="claude-opus-5-5",
        stop_reason="max_tokens",
        usage={"input_tokens": 20, "output_tokens": 10},
        content=[
            {"type": "tool_use", "id": "tool", "name": "lookup", "input": {"q": "a"}}
        ],
    )
    llm = AnthropicLargeLanguageModel()
    with pytest.raises(InvokeError, match="incomplete tool arguments.*max_tokens"):
        list(
            llm._handle_chat_generate_stream_response(
                response.model, {}, _stream(response, truncated=True), []
            )
        )
