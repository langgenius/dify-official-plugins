from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import auth


class GetProjectTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        jira = auth(self.runtime.credentials)

        project_key = tool_parameters.get("project_key")

        project = jira.get_project(project_key)
        if project is None:
            yield self.create_json_message(
                {
                    "error": f"Project with key {project_key} not found.",
                }
            )
            return

        yield self.create_json_message(project)
