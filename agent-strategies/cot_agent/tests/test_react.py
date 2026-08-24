import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from dify_plugin.entities.agent import AgentInvokeMessage
from dify_plugin.entities.model.llm import LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import AssistantPromptMessage
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.interfaces.agent import (
    AgentModelConfig,
    AgentScratchpadUnit,
    ToolEntity,
)

from strategies.ReAct import ReActAgentStrategy


class TestReActFileForwarding(unittest.TestCase):
    @staticmethod
    def _tool() -> ToolEntity:
        return ToolEntity.model_validate(
            {
                "identity": {
                    "author": "test",
                    "name": "getfile",
                    "label": {"en_US": "getfile"},
                    "provider": "workflow-provider",
                },
                "provider_type": "workflow",
                "runtime_parameters": {},
            }
        )

    def _handle(self, response: ToolInvokeMessage) -> tuple[str, list[ToolInvokeMessage]]:
        session = Mock()
        session.tool.invoke.return_value = iter([response])
        strategy = ReActAgentStrategy(runtime=Mock(), session=session)

        result, _, additional_messages = strategy._handle_invoke_action(
            action=AgentScratchpadUnit.Action(action_name="getfile", action_input={"a": "get"}),
            tool_instances={"getfile": self._tool()},
            message_file_ids=[],
        )
        return result, additional_messages

    def test_forwards_tool_file_link(self):
        response = ToolInvokeMessage(
            type=ToolInvokeMessage.MessageType.LINK,
            message=ToolInvokeMessage.TextMessage(text="/files/tools/file-1.docx"),
            meta={"tool_file_id": "file-1", "mime_type": "application/octet-stream"},
        )

        result, additional_messages = self._handle(response)

        self.assertIn("result link: /files/tools/file-1.docx", result)
        self.assertEqual(additional_messages, [response])

    def test_does_not_forward_plain_link(self):
        response = ToolInvokeMessage(
            type=ToolInvokeMessage.MessageType.LINK,
            message=ToolInvokeMessage.TextMessage(text="https://dify.ai"),
        )

        result, additional_messages = self._handle(response)

        self.assertIn("result link: https://dify.ai", result)
        self.assertEqual(additional_messages, [])


class TestReActSilentRoundTermination(unittest.TestCase):
    """Regression tests for issue #3699: ReAct rounds must not end silently."""

    @staticmethod
    def _tool() -> ToolEntity:
        return ToolEntity.model_validate(
            {
                "identity": {
                    "author": "test",
                    "name": "getfile",
                    "label": {"en_US": "getfile"},
                    "provider": "workflow-provider",
                },
                "provider_type": "workflow",
                "runtime_parameters": {},
                "parameters": [
                    {
                        "name": "q",
                        "label": {"en_US": "q"},
                        "human_description": {"en_US": "query"},
                        "type": "string",
                        "form": "llm",
                        "required": True,
                    }
                ],
            }
        )

    @staticmethod
    def _model() -> AgentModelConfig:
        return AgentModelConfig(
            provider="test-provider",
            model="test-model",
            mode="chat",
            completion_params={},
            history_prompt_messages=[],
        )

    @staticmethod
    def _llm_chunks(*contents: str) -> list[LLMResultChunk]:
        return [
            LLMResultChunk(
                model="test-model",
                delta=LLMResultChunkDelta(
                    index=0,
                    message=AssistantPromptMessage(content=content),
                    usage=None,
                ),
            )
            for content in contents
        ]

    def _strategy(
        self, llm_rounds: list[list[LLMResultChunk]], tool_result: str = "file-content"
    ) -> ReActAgentStrategy:
        session = Mock()
        session.model.llm.invoke.side_effect = [iter(round_chunks) for round_chunks in llm_rounds]
        session.tool.invoke.return_value = iter(
            [
                ToolInvokeMessage(
                    type=ToolInvokeMessage.MessageType.TEXT,
                    message=ToolInvokeMessage.TextMessage(text=tool_result),
                )
            ]
        )
        return ReActAgentStrategy(runtime=Mock(), session=session)

    def _run(self, strategy: ReActAgentStrategy, maximum_iterations: int = 1) -> list:
        return list(
            strategy._invoke(
                {
                    "query": "give me the file",
                    "instruction": "you are a helpful agent",
                    "model": self._model(),
                    "tools": [self._tool()],
                    "maximum_iterations": maximum_iterations,
                }
            )
        )

    @staticmethod
    def _error_logs(messages: list) -> list:
        return [
            message
            for message in messages
            if message.type == AgentInvokeMessage.MessageType.LOG
            and message.message.status == ToolInvokeMessage.LogMessage.LogStatus.ERROR
        ]

    @staticmethod
    def _texts(messages: list) -> list[str]:
        return [
            message.message.text
            for message in messages
            if message.type == AgentInvokeMessage.MessageType.TEXT
        ]

    def test_tool_call_wrapper_invokes_tool(self):
        # Issue #3699: a {"tool_call": {...}} wrapper used to end the round
        # silently; it must now be parsed as a tool call.
        raw = (
            '{"tool_call": {"thought": "get.", "action": "getfile", '
            '"action_input": {"q": "x"}}}'
        )
        strategy = self._strategy(
            [self._llm_chunks(raw), self._llm_chunks("FinalAnswer: done")]
        )
        messages = self._run(strategy, maximum_iterations=2)

        strategy.session.tool.invoke.assert_called_once()
        kwargs = strategy.session.tool.invoke.call_args.kwargs
        self.assertEqual(kwargs["tool_name"], "getfile")
        self.assertEqual(kwargs["parameters"], {"q": "x"})
        # the final answer is streamed chunk by chunk
        self.assertEqual("".join(self._texts(messages)).strip(), "done")

    def test_unparseable_output_surfaces_error_log(self):
        # Issue #3699 (2nd scenario): "Action_input: {...}" written as free
        # text must surface a visible error instead of ending the round
        # silently; the thought is still used as the final answer.
        raw = 'Thought: I need to search\nAction_input: {"input": "x"}'
        strategy = self._strategy([self._llm_chunks(raw)])
        messages = self._run(strategy)

        strategy.session.tool.invoke.assert_not_called()
        error_logs = self._error_logs(messages)
        self.assertEqual(len(error_logs), 1)
        self.assertEqual(error_logs[0].message.label, "Action parse failed")
        self.assertIn(
            "did not contain a valid Action", error_logs[0].message.data["error"]
        )
        self.assertEqual(
            self._texts(messages)[-1], 'I need to search\nAction_input: {"input": "x"}'
        )

    def test_direct_answer_without_prefix_still_succeeds(self):
        # A model that answers directly (no tool, no "FinalAnswer:" prefix)
        # must keep working without an error log.
        raw = "Thought: The capital of France is Paris."
        strategy = self._strategy([self._llm_chunks(raw)])
        messages = self._run(strategy)

        strategy.session.tool.invoke.assert_not_called()
        self.assertEqual(self._error_logs(messages), [])
        self.assertEqual(self._texts(messages)[-1], "The capital of France is Paris.")


if __name__ == "__main__":
    unittest.main()
