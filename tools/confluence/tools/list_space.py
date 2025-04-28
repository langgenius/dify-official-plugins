from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import auth


class ListSpaceTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        List all spaces in Confluence.
        """
        confluence = auth(self.runtime.credentials)

        spaces = confluence.get_all_spaces(
            start=0, limit=100, expand=None
        )  # default limit is 100

        yield self.create_json_message({"spaces": spaces})
