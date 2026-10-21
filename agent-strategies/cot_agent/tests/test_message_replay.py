import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.llm import (
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
    LLMUsage,
)
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    TextPromptMessageContent,
    UserPromptMessage,
)
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.interfaces.agent import AgentModelConfig, ToolEntity
from strategies.function_calling import FunctionCallingAgentStrategy
from strategies.ReAct import ReActAgentStrategy


@pytest.mark.parametrize("mode", ["blocking", "streaming", "react"])
def test_tool_rounds_preserve_original_messages_and_history(mode):
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
                        id=f"call-{index}",
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name="lookup", arguments="{}"
                        ),
                    )
                ],
            )
        )
    replies.append(AssistantPromptMessage(content="FinalAnswer: done"))
    requests = []

    def invoke(**kwargs):
        requests.append(deepcopy(kwargs["prompt_messages"]))
        reply = replies[len(requests) - 1]
        if mode == "blocking":
            return LLMResult(
                model=model.model,
                message=reply.model_copy(deep=True),
                usage=LLMUsage.empty_usage(),
            )
        return (
            chunk
            for chunk in [
                LLMResultChunk(
                    model=model.model,
                    delta=LLMResultChunkDelta(
                        index=0, message=reply.model_copy(deep=True)
                    ),
                ),
                LLMResultChunk(
                    model=model.model,
                    delta=LLMResultChunkDelta(
                        index=1, message=AssistantPromptMessage(content="")
                    ),
                ),
            ]
        )

    session = Mock()
    session.model.llm.invoke.side_effect = invoke
    session.tool.invoke.side_effect = lambda **_: iter(
        [
            ToolInvokeMessage(
                type=ToolInvokeMessage.MessageType.TEXT,
                message=ToolInvokeMessage.TextMessage(text=""),
            )
        ]
    )
    strategy_class = (
        ReActAgentStrategy if mode == "react" else FunctionCallingAgentStrategy
    )
    output = list(
        strategy_class(runtime=Mock(), session=session)._invoke(
            {
                "query": "look up",
                "instruction": "Use the tool",
                "model": model,
                "tools": [tool],
                "maximum_iterations": 3,
            }
        )
    )

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
