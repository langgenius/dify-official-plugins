import json
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools._client import DeepSeekClient


class DeepSeekSearchTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        query = tool_parameters.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > 128:
            raise ValueError(
                "Query must contain 1 to 128 characters and cannot be blank."
            )
        count = tool_parameters.get("count", 10)
        if (
            isinstance(count, bool)
            or not isinstance(count, (int, float))
            or not 1 <= count <= 50
            or int(count) != count
        ):
            raise ValueError("Result count must be an integer between 1 and 50.")
        need_content = tool_parameters.get("need_content", False)
        if not isinstance(need_content, bool):
            raise TypeError("Need content must be a boolean.")
        parameters = {"query": query, "count": int(count), "need_content": need_content}
        original_question = tool_parameters.get("ori_question")
        if original_question is not None and original_question != "":
            if (
                not isinstance(original_question, str)
                or not 1 <= len(original_question) <= 128
            ):
                raise ValueError("Original question must contain 1 to 128 characters.")
            parameters["ori_question"] = original_question
        localization = tool_parameters.get("localization")
        if localization is not None and localization != "":
            if not isinstance(localization, str):
                raise ValueError("Localization must be an IP address string.")
            parameters["localization"] = localization

        data = DeepSeekClient(self.runtime.credentials).search(parameters)
        yield self.create_json_message(data)
        yield self.create_text_message(json.dumps(data, ensure_ascii=False))
