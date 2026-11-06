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
        query = tool_parameters.get("query", "")
        if not query:
            yield self.create_text_message("Invalid parameter query")
        new_value = tool_parameters.get("new_value", "")
        if not new_value:
            yield self.create_text_message("Invalid parameter new_value")
        index = tool_parameters.get("index")
        create_path = tool_parameters.get("create_path", False)
        value_decode = tool_parameters.get("value_decode", False)
        ensure_ascii = tool_parameters.get("ensure_ascii", True)
        try:
            result = self._insert(content, query, new_value, ensure_ascii, value_decode, index, create_path)
            yield self.create_text_message(str(result))
        except Exception:
            yield self.create_text_message("Failed to insert JSON content")

    def _insert(
        self, origin_json, query, new_value, ensure_ascii: bool, value_decode: bool, index=None, create_path=False
    ):
        try:
            input_data = json.loads(origin_json)
            expr = parse(query)
            if value_decode is True:
                try:
                    new_value = json.loads(new_value)
                except json.JSONDecodeError:
                    return "Cannot decode new value to json object"
            matches = expr.find(input_data)
            if not matches and create_path:
                path_parts = query.strip("$").strip(".").split(".")
                current = input_data
                for i, part in enumerate(path_parts):
                    if "[" in part and "]" in part:
                        (array_name, index) = part.split("[")
                        index = int(index.rstrip("]"))
                        if array_name not in current:
                            current[array_name] = []
                        while len(current[array_name]) <= index:
                            current[array_name].append({})
                        current = current[array_name][index]
                    else:
                        if i == len(path_parts) - 1:
                            current[part] = new_value
                        elif part not in current:
                            current[part] = {}
                        current = current[part]
            else:
                for match in matches:
                    if isinstance(match.value, dict):
                        if isinstance(new_value, dict):
                            match.value.update(new_value)
                        else:
                            raise ValueError("Cannot insert non-dict value into dict")
                    elif isinstance(match.value, list):
                        if index is None:
                            match.value.append(new_value)
                        else:
                            match.value.insert(int(index), new_value)
                    else:
                        input_data = match.full_path.update(input_data, new_value)
            return json.dumps(input_data, ensure_ascii=ensure_ascii)
        except Exception as e:
            return str(e)
