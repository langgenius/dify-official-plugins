import sys
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
from dify_plugin.entities.model.message import AssistantPromptMessage
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeBadRequestError
from dify_plugin.interfaces.agent import AgentModelConfig, ToolEntity
from strategies.function_calling import FunctionCallingAgentStrategy
from strategies.ReAct import ReActAgentStrategy


@pytest.mark.parametrize("mode", ["blocking", "streaming", "react"])
@pytest.mark.parametrize("use_defaults", [False, True])
def test_provider_checks_context_without_changing_output_budget(mode, use_defaults):
    completion_params = (
        {}
        if use_defaults
        else {"max_tokens": 8192, "thinking": True, "thinking_budget": 4096}
    )
    model = AgentModelConfig(
        provider="test",
        model="test-model",
        mode="chat",
        completion_params=completion_params.copy(),
        entity=AIModelEntity.model_validate(
            {
                "model": "test-model",
                "label": {"en_US": "test-model"},
                "model_type": "llm",
                "features": ["stream-tool-call"] if mode == "streaming" else [],
                "model_properties": {"mode": "chat", "context_size": 16384},
                "parameter_rules": [
                    {
                        "name": "max_tokens",
                        "use_template": "max_tokens",
                        "default": 4096,
                    }
                ],
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
    tool_reply = AssistantPromptMessage(
        content="",
        tool_calls=[
            AssistantPromptMessage.ToolCall(
                id="call-1",
                type="function",
                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                    name="lookup", arguments="{}"
                ),
            )
        ],
    )
    if mode == "react":
        tool_reply = AssistantPromptMessage(
            content='{"thought":"look up the result","action":"lookup","action_input":{}}'
        )
    replies = [tool_reply, AssistantPromptMessage(content="FinalAnswer: done")]
    session = Mock()
    session.model.llm.invoke.side_effect = (
        [
            LLMResult(model=model.model, message=reply, usage=LLMUsage.empty_usage())
            for reply in replies
        ]
        if mode == "blocking"
        else [
            (
                chunk
                for chunk in [
                    LLMResultChunk(
                        model=model.model,
                        delta=LLMResultChunkDelta(index=0, message=reply),
                    )
                ]
            )
            for reply in replies
        ]
    )
    session.tool.invoke.return_value = iter(
        [
            ToolInvokeMessage(
                type=ToolInvokeMessage.MessageType.TEXT,
                message=ToolInvokeMessage.TextMessage(text="x " * 15000),
            )
        ]
    )
    strategy_class = (
        ReActAgentStrategy if mode == "react" else FunctionCallingAgentStrategy
    )
    strategy = strategy_class(runtime=Mock(), session=session)

    first_reply = session.model.llm.invoke.side_effect
    first_reply = next(first_reply)
    session.model.llm.invoke.side_effect = [
        first_reply,
        InvokeBadRequestError("provider context window exhausted"),
    ]

    with pytest.raises(InvokeBadRequestError, match="provider context window exhausted"):
        list(
            strategy._invoke(
                {
                    "query": "look up the result",
                    "instruction": "Use the tool",
                    "model": model,
                    "tools": [tool],
                    "maximum_iterations": 2,
                }
            )
        )

    session.tool.invoke.assert_called_once()
    assert session.model.llm.invoke.call_count == 2
    assert model.completion_params == completion_params
    for call in session.model.llm.invoke.call_args_list:
        assert call.kwargs["model_config"].completion_params == completion_params
