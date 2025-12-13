from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import auth


class ListProjectTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        
        jira = auth(self.runtime.credentials)

        yield self.create_json_message(
            {
                "projects": jira.projects(),
            }
        )
