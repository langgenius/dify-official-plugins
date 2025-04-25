from collections.abc import Generator
from typing import Any

from atlassian.jira import Jira
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListIssueTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        jira_url = self.runtime.credentials.get("jira_url")
        username = self.runtime.credentials.get("username")
        api_token = self.runtime.credentials.get("api_token")

        issue_key = tool_parameters.get("issue_key")

        jira = Jira(
            url=jira_url,
            username=username,
            password=api_token,
        )

        try:
            yield self.create_json_message(
                {
                    "issue": jira.issue(issue_key),
                }
            )

        except Exception as e:
            yield self.create_json_message(
                {
                    "error": f"Error occurred while fetching issues for board with ID {issue_key}: {str(e)}",
                }
            )
