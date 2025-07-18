from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import auth


class GetSpaceTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Get info of a space in Confluence.
        """
        confluence = auth(self.runtime.credentials)

        space_key = tool_parameters.get("space_key")

        space = confluence.get_space(
            space_key=space_key,
            expand=None,
        )

        if not space:
            yield self.create_text_message("Space not found")
            return

        yield self.create_json_message(space)
