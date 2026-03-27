from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.base import BailianMemoryBaseTool


class CreateProfileSchemaTool(BailianMemoryBaseTool, Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        attributes = self._parse_json_param(tool_parameters["attributes"], "attributes")

        body: dict[str, Any] = {"name": tool_parameters["name"], "attributes": attributes}
        description = tool_parameters.get("description", "")
        if description:
            body["description"] = description

        result = self._request("POST", "profile_schemas", json_body=body)
        yield self.create_json_message(result)
