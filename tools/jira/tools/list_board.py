from collections.abc import Generator
from typing import Any

from atlassian.jira import Jira
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListBoardTool(Tool):
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

        boards = jira.get_all_agile_boards(
            board_name=None, project_key=project_key, board_type=None, start=0, limit=50
        )  # Note: limit is 50 by default

        if not boards:
            yield self.create_json_message(
                {
                    "error": f"No boards found for project with key {project_key}.",
                }
            )

        yield self.create_json_message(
            {
                "boards": boards,
            }
        )
