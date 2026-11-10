import re
from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class RegexExpressionTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        content = tool_parameters.get("content", "")
        if not content:
            yield self.create_text_message("Invalid content")
        expression = tool_parameters.get("expression", "")
        if not expression:
            yield self.create_text_message("Invalid expression")
        try:
            result = re.findall(expression, content)
            yield self.create_text_message(str(result))
        except Exception as e:
            yield self.create_text_message(f"Failed to extract result, error: {str(e)}")
