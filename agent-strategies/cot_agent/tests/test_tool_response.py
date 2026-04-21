import json
import unittest

from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage

from tool_response import append_tool_result, render_tool_invoke_response


class ToolResponseTests(unittest.TestCase):
    def test_append_tool_result_preserves_order_and_duplicates(self):
        parts: list[str] = []

        append_tool_result(parts, "first")
        append_tool_result(parts, "first")
        append_tool_result(parts, "")
        append_tool_result(parts, "second")

        self.assertEqual(parts, ["first", "first", "second"])

    def test_render_text_response_keeps_verbatim_content(self):
        text = '{\n  "result": "ok"\n}\n'
        response = ToolInvokeMessage(
            type=ToolInvokeMessage.MessageType.TEXT,
            message=ToolInvokeMessage.TextMessage(text=text),
        )

        self.assertEqual(render_tool_invoke_response(response), text)

    def test_render_json_response_returns_single_layer_json(self):
        response = ToolInvokeMessage(
            type=ToolInvokeMessage.MessageType.JSON,
            message=ToolInvokeMessage.JsonMessage(json_object={"result": "ok"}),
        )

        rendered = render_tool_invoke_response(response)

        self.assertEqual(json.loads(rendered), {"result": "ok"})
        self.assertIsInstance(json.loads(rendered), dict)
        self.assertNotIn("tool response:", rendered)

    def test_render_link_response_keeps_existing_user_guidance(self):
        response = ToolInvokeMessage(
            type=ToolInvokeMessage.MessageType.LINK,
            message=ToolInvokeMessage.TextMessage(text="https://example.com"),
        )

        self.assertEqual(
            render_tool_invoke_response(response),
            "result link: https://example.com. please tell user to check it.",
        )

    def test_render_non_specialized_response_falls_back_to_string(self):
        response = ToolInvokeMessage(
            type=ToolInvokeMessage.MessageType.VARIABLE,
            message=InvokeMessage.VariableMessage(
                variable_name="result", variable_value={"result": "ok"}
            ),
        )

        rendered = render_tool_invoke_response(response)

        self.assertIn("result", rendered)
        self.assertIn("ok", rendered)


if __name__ == "__main__":
    unittest.main()
