from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.base import BailianMemoryBaseTool


class DeleteMemoryTool(BailianMemoryBaseTool, Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        memory_node_id = tool_parameters["memory_node_id"]
        result = self._request("DELETE", f"memory_nodes/{memory_node_id}")
        yield self.create_json_message(result)
