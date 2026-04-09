from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.base import BailianMemoryBaseTool


class SearchMemoryTool(BailianMemoryBaseTool, Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        body: dict[str, Any] = {
            "user_id": tool_parameters["user_id"],
            "messages": [{"role": "user", "content": tool_parameters["query"]}],
        }

        top_k = tool_parameters.get("top_k")
        min_score = tool_parameters.get("min_score")
        if top_k is not None:
            body["top_k"] = int(top_k)
        if min_score is not None:
            body["min_score"] = float(min_score)

        result = self._request("POST", "memory_nodes/search", json_body=body)
        yield self.create_json_message(result)
