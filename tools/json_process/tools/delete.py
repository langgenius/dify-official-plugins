import json
from typing import Any, Generator
from jsonpath_ng import parse
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class JSONDeleteTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the JSON delete tool
        """
        content = tool_parameters.get("content", "")
        if not content:
            yield self.create_text_message("Invalid parameter content")
        query = tool_parameters.get("query", "")
        if not query:
            yield self.create_text_message("Invalid parameter query")
        ensure_ascii = tool_parameters.get("ensure_ascii", True)
        try:
            result = self._delete(content, query, ensure_ascii)
            yield self.create_text_message(str(result))
        except Exception as e:
            yield self.create_text_message(f"Failed to delete JSON content: {str(e)}")

    def _delete(self, origin_json: str, query: str, ensure_ascii: bool) -> str:
        try:
            input_data = json.loads(origin_json)
            expr = parse("$." + query.lstrip("$."))
            matches = expr.find(input_data)
            if not matches:
                return json.dumps(input_data, ensure_ascii=ensure_ascii)
            array_deletions = {}
            for match in matches:
                if isinstance(match.context.value, dict):
                    del match.context.value[match.path.fields[-1]]
                elif isinstance(match.context.value, list):
                    array = match.context.value
                    indices = array_deletions.setdefault(id(array), (array, set()))[1]
                    indices.update(index % len(array) for index in match.path.indices)
                else:
                    parent = match.context.parent
                    if parent:
                        del parent.value[match.path.fields[-1]]
            # Remove original positions once, from right to left, without comparing values.
            for array, indices in array_deletions.values():
                for index in sorted(indices, reverse=True):
                    del array[index]
            return json.dumps(input_data, ensure_ascii=ensure_ascii)
        except Exception as e:
            raise Exception(f"Delete operation failed: {str(e)}")
