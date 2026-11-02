import json
import sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dify_plugin.core.runtime import Session
from dify_plugin.core.server.stdio.request_reader import StdioRequestReader
from dify_plugin.core.server.stdio.response_writer import StdioResponseWriter
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.llm import LLMResultChunk, LLMResultChunkDelta, LLMUsage
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    TextPromptMessageContent,
    UserPromptMessage,
    ensure_prompt_message,
)
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.interfaces.agent import AgentModelConfig, ToolEntity
from strategies.function_calling import FunctionCallingAgentStrategy
from strategies.ReAct import ReActAgentStrategy


@pytest.mark.parametrize("mode", ["blocking", "streaming", "react"])
@pytest.mark.parametrize("fail_after_call", [False, True])
def test_tool_rounds_preserve_original_messages_and_history(
    mode, fail_after_call, monkeypatch
):
    history = [
        UserPromptMessage(
            content=[
                ImagePromptMessageContent(
                    format="png",
                    mime_type="image/png",
                    base64_data="cG5n",
                    detail="low",
                )
            ]
        ),
        AssistantPromptMessage(content="Earlier answer", opaque_body={"earlier": True}),
    ]
    original_history = deepcopy(history)
    model = AgentModelConfig(
        provider="gemini",
        model="test-model",
        mode="chat",
        completion_params={},
        history_prompt_messages=history,
        entity=AIModelEntity.model_validate(
            {
                "model": "test-model",
                "label": {"en_US": "test-model"},
                "model_type": "llm",
                "features": ["vision", "stream-tool-call"]
                if mode == "streaming"
                else ["vision"],
                "model_properties": {"mode": "chat"},
                "parameter_rules": [],
            }
        ),
    )
    tool = ToolEntity.model_validate(
        {
            "identity": {
                "author": "test",
                "name": "lookup",
                "label": {"en_US": "lookup"},
                "provider": "test",
            },
            "provider_type": "workflow",
            "runtime_parameters": {},
        }
    )
    replies = []
    for index, snapshot in enumerate(
        ({"signature": "signed", "id": 9007199254740993}, False)
    ):
        text = (
            '{"thought":"look up","action":"lookup","action_input":{}}'
            if mode == "react"
            else "looking up"
        )
        replies.append(
            AssistantPromptMessage(
                content=[
                    TextPromptMessageContent(data=text, opaque_body={"block": index}),
                    TextPromptMessageContent(data="", opaque_body=0),
                ],
                opaque_body=snapshot,
                tool_calls=[]
                if mode == "react"
                else [
                    AssistantPromptMessage.ToolCall(
                        id=f"call-{index}-{call_index}",
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name="lookup",
                            arguments='{ "id": 9007199254740993, "scale": 1e-9, "label": "\\u4e2d" }',
                        ),
                    )
                    for call_index in range(2)
                ],
            )
        )
    replies.append(AssistantPromptMessage(content="FinalAnswer: done"))
    requests = []
    tool_requests = []

    def respond(request):
        invocation = json.loads(request.content)["data"]["data"]
        if invocation["type"] == "tool":
            tool_requests.append(invocation["request"])
            messages = [
                ToolInvokeMessage(
                    type=ToolInvokeMessage.MessageType.TEXT,
                    message=ToolInvokeMessage.TextMessage(text=""),
                ).model_dump(mode="json")
            ]
        else:
            assert invocation["type"] == "llm"
            requests.append(
                [
                    ensure_prompt_message(value)
                    for value in invocation["request"]["prompt_messages"]
                ]
            )
            round_index = len(requests) - 1
            reply = replies[round_index]
            partial = reply.model_copy(deep=True)
            terminal = AssistantPromptMessage(content="")
            if isinstance(reply.content, list):
                partial.content = reply.content[:1]
                partial.tool_calls = reply.tool_calls[:1]
                terminal.content = reply.content[1:]
                terminal.tool_calls = reply.tool_calls[1:]
            terminal.opaque_body = partial.opaque_body
            partial.opaque_body = None
            partial_usage = LLMUsage.empty_usage()
            partial_usage.prompt_tokens = 10
            partial_usage.completion_tokens = 1
            partial_usage.total_tokens = 11
            partial_usage.total_price = Decimal("0.01")
            terminal_usage = partial_usage.model_copy(
                update={
                    "prompt_tokens": 10 * (round_index + 1),
                    "completion_tokens": round_index + 3,
                    "total_tokens": 11 * (round_index + 1) + 2,
                    "total_price": Decimal("0.1") * (round_index + 1),
                }
            )
            messages = [
                LLMResultChunk(
                    model=model.model,
                    delta=LLMResultChunkDelta(
                        index=index, message=message, usage=usage
                    ),
                ).model_dump(mode="json")
                for index, (message, usage) in enumerate(
                    [
                        (partial, partial_usage),
                        (terminal, terminal_usage),
                        (AssistantPromptMessage(content=""), None),
                    ]
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
                    "data": message,
                },
            }
            for message in messages
        ]
        if fail_after_call and invocation["type"] == "llm":
            events = events[:1] + [
                {
                    "session_id": "replay",
                    "event": "backwards_response",
                    "data": {
                        "backwards_request_id": invocation["backwards_request_id"],
                        "event": "error",
                        "message": "provider stream failed",
                        "data": None,
                    },
                }
            ]
        return httpx.Response(200, text="\n".join(map(json.dumps, events)))

    client_type = httpx.Client
    monkeypatch.setattr(
        "dify_plugin.core.runtime.httpx",
        SimpleNamespace(
            Client=lambda: client_type(transport=httpx.MockTransport(respond))
        ),
    )
    strategy_class = (
        ReActAgentStrategy if mode == "react" else FunctionCallingAgentStrategy
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        session = Session(
            session_id="replay",
            executor=executor,
            reader=StdioRequestReader(),
            writer=StdioResponseWriter(),
            dify_plugin_daemon_url="http://daemon.test",
        )
        invocation = strategy_class(runtime=Mock(), session=session)._invoke(
            {
                "query": "look up",
                "instruction": "Use the tool",
                "model": model,
                "tools": [tool],
                "maximum_iterations": 3,
            }
        )
        if fail_after_call:
            with pytest.raises(Exception, match="provider stream failed"):
                list(invocation)
            assert tool_requests == []
            return
        output = list(invocation)

    assert len(tool_requests) == (2 if mode == "react" else 4)
    if mode != "react":
        assert all(
            request["tool_parameters"]
            == {"id": 9007199254740993, "scale": 1e-9, "label": "中"}
            for request in tool_requests
        )
    metadata = next(
        item.message.json_object
        for item in output
        if item.type == ToolInvokeMessage.MessageType.JSON
        and "model_history" in item.message.json_object
    )
    usage = metadata.get("execution_metadata", metadata)
    assert usage["total_tokens"] == 72
    assert float(usage["total_price"]) == pytest.approx(0.6)

    assert len(requests) == 3
    assert model.history_prompt_messages == original_history
    for request in requests[1:]:
        assert request[: len(requests[0])] == requests[0]
    assistants = [
        message
        for message in requests[-1]
        if isinstance(message, AssistantPromptMessage)
    ]
    assert assistants[-2:] == replies[:2]
    assert type(assistants[-1].opaque_body) is bool

    saved = next(
        item.message.json_object["model_history"]
        for item in output
        if item.type == ToolInvokeMessage.MessageType.JSON
        and "model_history" in item.message.json_object
    )
    restored_model = AgentModelConfig.model_validate(
        {**model.model_dump(mode="json"), "history_prompt_messages": saved["messages"]}
    )
    restored_assistants = [
        message
        for message in restored_model.history_prompt_messages
        if isinstance(message, AssistantPromptMessage)
    ]
    assert restored_assistants == replies
    assert saved["provider"] == model.provider
    assert saved["model"] == model.model
