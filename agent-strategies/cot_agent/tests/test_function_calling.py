import json
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from dify_plugin.entities import I18nObject
from dify_plugin.entities.model import AIModelEntity, ModelType
from dify_plugin.entities.model.llm import LLMResult, LLMUsage
from dify_plugin.entities.model.message import AssistantPromptMessage, ToolPromptMessage
from dify_plugin.entities.tool import ToolInvokeMessage, ToolProviderType
from dify_plugin.interfaces.agent import AgentModelConfig, AgentToolIdentity, ToolEntity

from strategies.function_calling import FunctionCallingAgentStrategy


def make_usage() -> LLMUsage:
    return LLMUsage(
        prompt_tokens=1,
        prompt_unit_price=Decimal("0"),
        prompt_price_unit=Decimal("0"),
        prompt_price=Decimal("0"),
        completion_tokens=1,
        completion_unit_price=Decimal("0"),
        completion_price_unit=Decimal("0"),
        completion_price=Decimal("0"),
        total_tokens=2,
        total_price=Decimal("0"),
        currency="USD",
        latency=0.0,
    )


def make_tool_call(name: str, arguments: dict) -> AssistantPromptMessage.ToolCall:
    return AssistantPromptMessage.ToolCall(
        id="call-1",
        type="function",
        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
            name=name,
            arguments=json.dumps(arguments),
        ),
    )


def make_result(
    content: str, tool_calls: list[AssistantPromptMessage.ToolCall]
) -> LLMResult:
    return LLMResult(
        model="mock-model",
        message=AssistantPromptMessage(content=content, tool_calls=tool_calls),
        usage=make_usage(),
    )


def make_model_config() -> AgentModelConfig:
    return AgentModelConfig(
        provider="mock-provider",
        model="mock-model",
        mode="chat",
        completion_params={},
        entity=AIModelEntity(
            model="mock-model",
            label=I18nObject(en_US="Mock Model"),
            model_type=ModelType.LLM,
            features=[],
            model_properties={},
        ),
        history_prompt_messages=[],
    )


def make_tool_entity() -> ToolEntity:
    return ToolEntity(
        identity=AgentToolIdentity(
            author="tester",
            name="lookup",
            label=I18nObject(en_US="Lookup"),
            provider="mock-provider",
        ),
        provider_type=ToolProviderType.BUILT_IN,
        runtime_parameters={"tenant": "dify"},
    )


class FakeLLM:
    def __init__(self):
        self.prompt_messages_history: list[list] = []
        self._results = [
            make_result("", [make_tool_call("lookup", {"query": "hello"})]),
            make_result("done", []),
        ]

    def invoke(self, model_config, prompt_messages, stop, stream, tools):
        self.prompt_messages_history.append(prompt_messages)
        return self._results[len(self.prompt_messages_history) - 1]


class FakeToolRuntime:
    def __init__(self, responses: list[ToolInvokeMessage]):
        self.responses = responses
        self.calls: list[dict] = []

    def invoke(self, **kwargs):
        self.calls.append(kwargs)
        return list(self.responses)


class FunctionCallingToolResponseTests(unittest.TestCase):
    def _run_strategy(self, responses: list[ToolInvokeMessage]) -> tuple[str, FakeToolRuntime]:
        llm = FakeLLM()
        tool_runtime = FakeToolRuntime(responses)
        session = SimpleNamespace(
            model=SimpleNamespace(llm=llm),
            tool=SimpleNamespace(invoke=tool_runtime.invoke),
        )
        strategy = FunctionCallingAgentStrategy(
            runtime=SimpleNamespace(), session=session
        )

        parameters = {
            "query": "hello",
            "instruction": "Use tools when needed",
            "model": make_model_config(),
            "tools": [make_tool_entity()],
            "maximum_iterations": 2,
            "context": None,
        }

        with (
            patch.object(FunctionCallingAgentStrategy, "_init_prompt_tools", return_value=[]),
            patch.object(FunctionCallingAgentStrategy, "update_prompt_message_tool"),
        ):
            list(strategy._invoke(parameters))

        second_round_messages = llm.prompt_messages_history[1]
        tool_messages = [
            message
            for message in second_round_messages
            if isinstance(message, ToolPromptMessage)
        ]

        self.assertEqual(len(tool_messages), 1)
        return str(tool_messages[0].content), tool_runtime

    def test_invoke_feeds_json_tool_output_without_tool_response_prefix(self):
        content, tool_runtime = self._run_strategy(
            [
                ToolInvokeMessage(
                    type=ToolInvokeMessage.MessageType.JSON,
                    message=ToolInvokeMessage.JsonMessage(json_object={"result": "ok"}),
                )
            ]
        )

        self.assertEqual(json.loads(content), {"result": "ok"})
        self.assertIsInstance(json.loads(content), dict)
        self.assertNotIn("tool response:", content)
        self.assertEqual(
            tool_runtime.calls[0]["parameters"],
            {"tenant": "dify", "query": "hello"},
        )

    def test_invoke_preserves_text_tool_output_exactly(self):
        text = '{\n  "result": "ok"\n}\n'
        content, _ = self._run_strategy(
            [
                ToolInvokeMessage(
                    type=ToolInvokeMessage.MessageType.TEXT,
                    message=ToolInvokeMessage.TextMessage(text=text),
                )
            ]
        )

        self.assertEqual(content, text)


if __name__ == "__main__":
    unittest.main()
