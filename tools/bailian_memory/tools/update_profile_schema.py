from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.base import BailianMemoryBaseTool


class UpdateProfileSchemaTool(BailianMemoryBaseTool, Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        profile_schema_id = tool_parameters["profile_schema_id"]
        name = tool_parameters.get("name", "")
        description = tool_parameters.get("description", "")
        attributes_operations_str = tool_parameters.get("attributes_operations", "")

        body: dict[str, Any] = {}
        if name:
            body["name"] = name
        if description:
            body["description"] = description
        if attributes_operations_str:
            body["attributes_operations"] = self._parse_json_param(
                attributes_operations_str, "attributes_operations"
            )

        if not body:
            yield self.create_text_message(
                "At least one of 'name', 'description', or 'attributes_operations' must be provided."
            )
            return

        result = self._request("PATCH", f"profile_schemas/{profile_schema_id}", json_body=body)
        yield self.create_json_message(result)
