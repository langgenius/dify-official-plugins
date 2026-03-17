from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.base import BailianMemoryBaseTool


class DeleteProfileSchemaTool(BailianMemoryBaseTool, Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        profile_schema_id = tool_parameters["profile_schema_id"]
        result = self._request("DELETE", f"profile_schemas/{profile_schema_id}")
        yield self.create_json_message(result)
