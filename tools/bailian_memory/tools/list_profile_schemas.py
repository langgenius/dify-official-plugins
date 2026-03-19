from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.base import BailianMemoryBaseTool


class ListProfileSchemasTool(BailianMemoryBaseTool, Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        params: dict[str, Any] = {}
        page_num = tool_parameters.get("page_num")
        page_size = tool_parameters.get("page_size")
        if page_num is not None:
            params["page_num"] = int(page_num)
        if page_size is not None:
            params["page_size"] = int(page_size)

        result = self._request("GET", "profile_schemas", params=params)
        yield self.create_json_message(result)
