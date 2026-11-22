import json
from typing import Any, Generator
from jsonpath_ng import parse
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class JSONParseTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        content = tool_parameters.get("content", "")
        if not content:
            yield self.create_text_message("Invalid parameter content")
            return
        json_filter = tool_parameters.get("json_filter", "")
        if not json_filter:
            yield self.create_text_message("Invalid parameter json_filter")
            return
        ensure_ascii = tool_parameters.get("ensure_ascii", True)
        try:
            result = self._extract(content, json_filter, ensure_ascii)
            yield self.create_text_message(str(result))
        except Exception:
            yield self.create_text_message("Failed to extract JSON content")

    def _extract(self, content: str, json_filter: str, ensure_ascii: bool) -> str:
        try:
            input_data = json.loads(content)
            expr = parse(json_filter)
            result = [match.value for match in expr.find(input_data)]
            if not result:
                return ""
            if len(result) == 1:
                result = result[0]
            if isinstance(result, dict | list):
                return json.dumps(result, ensure_ascii=ensure_ascii)
            elif isinstance(result, str | int | float | bool) or result is None:
                return str(result)
            else:
                return repr(result)
        except Exception as e:
            return str(e)
