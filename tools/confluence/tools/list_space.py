from collections.abc import Generator
from typing import Any

from atlassian import ConfluenceV2
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import connect


class ListSpaceTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        List all spaces in Confluence.
        """
        confluence = yield from connect(self)
        if confluence is None:
            return

        if isinstance(confluence, ConfluenceV2):
            spaces = confluence.get_spaces(limit=100)
        else:
            spaces = confluence.get_all_spaces(start=0, limit=100, expand=None)

        yield self.create_json_message({"spaces": spaces})
