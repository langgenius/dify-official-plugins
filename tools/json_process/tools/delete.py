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
            # Collect list-element removals first so that every matched position
            # refers to the original list, then delete by position in descending
            # order. Deferring the mutation avoids the off-by-one that a naive
            # per-match ``list.remove``/``del`` introduces for wildcard and
            # duplicate-value matches.
            list_removals: dict[int, tuple[list, set[int]]] = {}
            for match in matches:
                if isinstance(match.context.value, dict):
                    del match.context.value[match.path.fields[-1]]
                elif isinstance(match.context.value, list):
                    indices = getattr(match.path, "indices", None)
                    if indices:
                        target = match.context.value
                        bucket = list_removals.setdefault(id(target), (target, set()))
                        # Normalize negative indices against the original list
                        # length so they stay correct regardless of later
                        # removals.
                        for i in indices:
                            if i < 0:
                                i += len(target)
                            if 0 <= i < len(target):
                                bucket[1].add(i)
                else:
                    parent = match.context.parent
                    if parent:
                        del parent.value[match.path.fields[-1]]

            for target, indices in list_removals.values():
                for index in sorted(indices, reverse=True):
                    if 0 <= index < len(target):
                        del target[index]

            return json.dumps(input_data, ensure_ascii=ensure_ascii)
        except Exception as e:
            raise Exception(f"Delete operation failed: {str(e)}")
