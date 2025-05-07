from collections.abc import Generator
from typing import Any

from atlassian.jira import Jira
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListIssueTypeTool(Tool):
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

        project = jira.project(project_key)
        if not project:
            yield self.create_text_message(f"Project with key {project_key} not found.")
            return

        yield self.create_json_message(
            jira.issue_createmeta_issuetypes(
                project, start=None, limit=None
            )  # Get create metadata issue types for a project
        )
