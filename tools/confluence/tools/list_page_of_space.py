from collections.abc import Generator
from typing import Any

from atlassian import ConfluenceV2
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

        if isinstance(confluence, ConfluenceV2):
            space = confluence.get_space_by_key(space_key)
            pages = confluence.get_pages(space_id=space["id"], limit=100, get_body=True)
        else:
            pages = list(confluence.get_all_pages_from_space(space_key, limit=100))

        yield self.create_json_message({"pages": pages})
