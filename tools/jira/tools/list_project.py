from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import connect


class ListProjectTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        
        jira = yield from connect(self)
        if jira is None:
            return

        yield self.create_json_message(
            {
                "projects": jira.projects(),
            }
        )
