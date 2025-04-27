from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import auth


class CreatePageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Create a page in selected space in Confluence.
        """
        confluence = auth(self.runtime.credentials)
        space_key = tool_parameters.get("space_key")
        title = tool_parameters.get("title")
        body = tool_parameters.get("body")

        space = confluence.get_space(space_key)
        if not space:
            yield self.create_text_message("Space not found")
            return

        try:
            _ = confluence.create_page(
                space=space_key,
                title=title,
                body=body,
                representation="storage",
            )
            yield self.create_text_message("Page created successfully")

        except Exception as e:
            yield self.create_text_message(f"Failed to create page: {str(e)}")
            return
