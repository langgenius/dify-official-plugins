import json
from typing import Any, Generator
from jsonpath_ng import parse
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class JSONReplaceTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        content = tool_parameters.get("content", "")
        if not content:
            yield self.create_text_message("Invalid parameter content")
        query = tool_parameters.get("query", "")
        if not query:
            yield self.create_text_message("Invalid parameter query")
        replace_value = tool_parameters.get("replace_value", "")
        if not replace_value:
            yield self.create_text_message("Invalid parameter replace_value")
        replace_model = tool_parameters.get("replace_model", "")
        if not replace_model:
            yield self.create_text_message("Invalid parameter replace_model")
        value_decode = tool_parameters.get("value_decode", False)
        ensure_ascii = tool_parameters.get("ensure_ascii", True)
        try:
            if replace_model == "pattern":
                replace_pattern = tool_parameters.get("replace_pattern", "")
                if not replace_pattern:
                    yield self.create_text_message("Invalid parameter replace_pattern")
                result = self._replace_pattern(
                    content, query, replace_pattern, replace_value, ensure_ascii, value_decode
                )
            elif replace_model == "key":
                result = self._replace_key(content, query, replace_value, ensure_ascii)
            elif replace_model == "value":
                result = self._replace_value(content, query, replace_value, ensure_ascii, value_decode)
            yield self.create_text_message(str(result))
        except Exception:
            yield self.create_text_message("Failed to replace JSON content")

    def _replace_pattern(
        self, content: str, query: str, replace_pattern: str, replace_value: str, ensure_ascii: bool, value_decode: bool
    ) -> str:
        try:
            input_data = json.loads(content)
            expr = parse(query)
            matches = expr.find(input_data)
            for match in matches:
                new_value = match.value.replace(replace_pattern, replace_value)
                if value_decode is True:
                    try:
                        new_value = json.loads(new_value)
                    except json.JSONDecodeError:
                        return "Cannot decode replace value to json object"
                input_data = match.full_path.update(input_data, new_value)
            return json.dumps(input_data, ensure_ascii=ensure_ascii)
        except Exception as e:
            return str(e)

    def _replace_key(self, content: str, query: str, replace_value: str, ensure_ascii: bool) -> str:
        try:
            input_data = json.loads(content)
            expr = parse(query)
            matches = expr.find(input_data)
            for match in matches:
                parent = match.context.value
                if isinstance(parent, dict):
                    old_key = match.path.fields[0]
                    if old_key in parent:
                        value = parent.pop(old_key)
                        parent[replace_value] = value
                elif isinstance(parent, list):
                    for item in parent:
                        if isinstance(item, dict) and old_key in item:
                            value = item.pop(old_key)
                            item[replace_value] = value
            return json.dumps(input_data, ensure_ascii=ensure_ascii)
        except Exception as e:
            return str(e)

    def _replace_value(
        self, content: str, query: str, replace_value: str, ensure_ascii: bool, value_decode: bool
    ) -> str:
        try:
            input_data = json.loads(content)
            expr = parse(query)
            if value_decode is True:
                try:
                    replace_value = json.loads(replace_value)
                except json.JSONDecodeError:
                    return "Cannot decode replace value to json object"
            matches = expr.find(input_data)
            for match in matches:
                input_data = match.full_path.update(input_data, replace_value)
            return json.dumps(input_data, ensure_ascii=ensure_ascii)
        except Exception as e:
            return str(e)
