from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.base import BailianMemoryBaseTool


class AddMemoryTool(BailianMemoryBaseTool, Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        user_id = tool_parameters["user_id"]
        messages_str = tool_parameters.get("messages", "")
        custom_content = tool_parameters.get("custom_content", "")
        profile_schema_id = tool_parameters.get("profile_schema_id", "")
        meta_data_str = tool_parameters.get("meta_data", "")

        if not messages_str and not custom_content:
            yield self.create_text_message(
                "Either 'messages' or 'custom_content' must be provided."
            )
            return

        body: dict[str, Any] = {"user_id": user_id}

        if messages_str:
            body["messages"] = self._parse_json_param(messages_str, "messages")
        if custom_content:
            body["custom_content"] = custom_content
        if profile_schema_id:
            body["profile_schema"] = profile_schema_id
        if meta_data_str:
            body["meta_data"] = self._parse_json_param(meta_data_str, "meta_data")

        result = self._request("POST", "add", json_body=body)
        yield self.create_json_message(result)
