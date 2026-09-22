import json
from pathlib import Path
from unittest.mock import Mock

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
from dify_plugin.entities.model import AIModelEntity, ModelFeature
from dify_plugin.entities.model.llm import LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    UserPromptMessage,
)
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError
from dify_plugin.file.file import File, FileType
from dify_plugin.interfaces.agent import AgentModelConfig, ToolEntity

from models.llm.llm import AnthropicLargeLanguageModel


def _stream(response, truncated=False):
    yield MessageStartEvent(type="message_start", message=response.model_copy(update={"content": []}))
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
        yield ContentBlockStartEvent(type="content_block_start", index=index, content_block=start)
        for delta in deltas:
            yield ContentBlockDeltaEvent(type="content_block_delta", index=index, delta=delta)
        yield ContentBlockStopEvent(type="content_block_stop", index=index)
    yield MessageDeltaEvent(
        type="message_delta",
        delta={"stop_reason": "max_tokens" if truncated else "tool_use", "stop_sequence": None},
        usage={"output_tokens": 10},
    )
    yield MessageStopEvent(type="message_stop")


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("with_image", [False, True])
def test_agent_replays_each_assistants_original_signed_content(stream, with_image, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3] / "agent-strategies/cot_agent"))
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
            id=f"msg_{turn}", type="message", role="assistant", model="claude-opus-5-5",
            stop_reason="tool_use", usage={"input_tokens": 20, "output_tokens": 10},
            content=[
                {"type": "thinking", "thinking": "", "signature": f"omitted_{turn}"},
                {"type": "text", "text": f"Checking {turn}"},
                {"type": "tool_use", "id": f"tool_{turn}_a", "name": "lookup", "input": {"q": "a"}},
                {"type": "redacted_thinking", "data": f"encrypted_{turn}"},
                {"type": "thinking", "thinking": "Next check", "signature": f"progress_{turn}"},
                {"type": "tool_use", "id": f"tool_{turn}_b", "name": "lookup", "input": {"q": "b"}},
            ],
        )
        responses.append(response)
        expected.append([block.model_dump(mode="json", exclude_none=True) for block in response.content])

    responses.append(Message(
        id="done", type="message", role="assistant", model="claude-opus-5-5",
        stop_reason="end_turn", usage={"input_tokens": 20, "output_tokens": 10},
        content=[{"type": "text", "text": "Done"}],
    ))
    histories = []
    requests = []

    def invoke(**kwargs):
        assert kwargs["stream"] is stream
        # The agent and provider exchange JSON, and each invocation can use a new instance.
        history = [type(message).model_validate_json(message.model_dump_json())
                   for message in kwargs["prompt_messages"]]
        llm = AnthropicLargeLanguageModel(model_schemas=[entity])
        _, messages = llm._convert_prompt_messages(history)
        histories.append(history)
        requests.append(messages)
        response = responses[len(requests) - 1]
        if stream:
            chunks = list(llm._handle_chat_generate_stream_response(response.model, {}, _stream(response), history))
            # A later chunk without metadata must not erase the signed content.
            chunks.append(LLMResultChunk(model=response.model, delta=LLMResultChunkDelta(
                index=len(chunks), message=AssistantPromptMessage(content=""),
            )))
            return (LLMResultChunk.model_validate_json(chunk.model_dump_json()) for chunk in chunks)
        result = llm._handle_chat_generate_response(response.model, {}, response, history)
        return type(result).model_validate_json(result.model_dump_json())

    session = Mock()
    session.model.llm.invoke.side_effect = invoke
    session.tool.invoke.side_effect = lambda **kwargs: iter([ToolInvokeMessage(
        type=ToolInvokeMessage.MessageType.TEXT,
        message=ToolInvokeMessage.TextMessage(text="Found"),
    )])
    strategy = FunctionCallingAgentStrategy(runtime=Mock(), session=session)
    image = File(url="https://example.invalid/image.png", mime_type="image/png",
                 filename="image.png", extension=".png", size=3, type=FileType.IMAGE)
    image._blob = b"png"
    list(strategy._invoke({
        "query": "Second question", "instruction": "Use lookup",
        "files": [image] if with_image else [],
        "model": AgentModelConfig(
            provider="anthropic", model="claude-opus-5-5", mode="chat", entity=entity,
            history_prompt_messages=[
                UserPromptMessage(content="First question"),
                AssistantPromptMessage(content="Earlier ordinary answer"),
            ],
        ),
        "tools": [ToolEntity.model_validate({
            "identity": {"author": "test", "name": "lookup", "label": {"en_US": "lookup"}, "provider": "test"},
            "provider_type": "mcp", "runtime_parameters": {},
        })],
        "maximum_iterations": 3,
    }))

    assert len(requests) == 3
    assert session.tool.invoke.call_count == 4
    for turn, messages in enumerate(requests):
        assert messages[:3] == requests[0][:3]
        assistants = [message["content"] for message in messages if message["role"] == "assistant"]
        assert assistants == [[{"type": "text", "text": "Earlier ordinary answer"}], *expected[:turn]]
    assistants[-1][0]["signature"] = "changed"
    _, messages = AnthropicLargeLanguageModel()._convert_prompt_messages(histories[-1])
    assert [message["content"] for message in messages if message["role"] == "assistant"][1:] == expected


def test_truncated_tool_arguments_raise_an_actionable_invoke_error():
    response = Message(
        id="truncated", type="message", role="assistant", model="claude-opus-5-5",
        stop_reason="max_tokens", usage={"input_tokens": 20, "output_tokens": 10},
        content=[{"type": "tool_use", "id": "tool", "name": "lookup", "input": {"q": "a"}}],
    )
    llm = AnthropicLargeLanguageModel()
    with pytest.raises(InvokeError, match="incomplete tool arguments.*max_tokens"):
        list(llm._handle_chat_generate_stream_response(response.model, {}, _stream(response, truncated=True), []))
