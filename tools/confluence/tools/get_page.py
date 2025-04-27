from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import auth


class GetPageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Get info of a page (including content) in Confluence.
        """
        confluence = auth(self.runtime.credentials)

        page_id = tool_parameters.get("page_id")

        page = confluence.get_page_by_id(page_id, expand="body.storage")
        if not page:
            yield self.create_text_message("Page not found")
            return

        yield self.create_json_message(page)
