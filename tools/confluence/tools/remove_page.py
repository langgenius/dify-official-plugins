from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import auth


class RemovePageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Remove a page in Confluence.
        """
        confluence = auth(self.runtime.credentials)

        page_id = tool_parameters.get("page_id")

        page = confluence.get_page_by_id(page_id)
        if not page:
            yield ToolInvokeMessage(self.create_text_message("Page not found"))
            return

        try:
            _ = confluence.remove_page(page_id)
            yield self.create_text_message("Page removed successfully")
        except Exception as e:
            yield self.create_text_message(f"Failed to remove page: {str(e)}")
            return
