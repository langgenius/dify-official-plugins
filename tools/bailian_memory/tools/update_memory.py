from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.base import BailianMemoryBaseTool


class UpdateMemoryTool(BailianMemoryBaseTool, Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        memory_node_id = tool_parameters["memory_node_id"]
        body: dict[str, Any] = {
            "user_id": tool_parameters["user_id"],
            "custom_content": tool_parameters["custom_content"],
        }

        meta_data_str = tool_parameters.get("meta_data", "")
        if meta_data_str:
            body["meta_data"] = self._parse_json_param(meta_data_str, "meta_data")

        result = self._request("PATCH", f"memory_nodes/{memory_node_id}", json_body=body)
        yield self.create_json_message(result)
