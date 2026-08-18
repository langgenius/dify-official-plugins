import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.interfaces.agent import AgentScratchpadUnit, ToolEntity

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


if __name__ == "__main__":
    unittest.main()
