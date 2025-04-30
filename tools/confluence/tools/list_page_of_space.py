from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import auth


class ListPageofSpaceTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        List all pages in a space in Confluence.
        """
        confluence = auth(self.runtime.credentials)

        space_key = tool_parameters.get("space_key")

        pages = confluence.get_all_pages_from_space(
            space_key, start=0, limit=100, status=None, expand=None, content_type="page"
        )

        yield self.create_json_message({"pages": pages})
