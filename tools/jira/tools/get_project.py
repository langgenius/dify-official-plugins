from collections.abc import Generator
from typing import Any

from atlassian.jira import Jira
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class GetProjectTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        jira_url = self.runtime.credentials.get("jira_url")
        username = self.runtime.credentials.get("username")
        api_token = self.runtime.credentials.get("api_token")

        project_key = tool_parameters.get("project_key")

        jira = Jira(
            url=jira_url,
            username=username,
            password=api_token,
        )

        project = jira.get_project(project_key)
        if project is None:
            yield self.create_json_message(
                {
                    "error": f"Project with key {project_key} not found.",
                }
            )
            return

        yield self.create_json_message(project)
