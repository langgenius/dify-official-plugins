from collections.abc import Generator
from typing import Any

from atlassian.jira import Jira
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class DeleteIssueTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        jira_url = self.runtime.credentials.get("jira_url")
        username = self.runtime.credentials.get("username")
        api_token = self.runtime.credentials.get("api_token")

        issue_id = tool_parameters.get("issue_id")

        jira = Jira(
            url=jira_url,
            username=username,
            password=api_token,
        )

        issue = jira.issue(issue_id)
        if not issue:
            yield self.create_text_message(f"Issue with ID {issue_id} not found.")
            return

        try:
            jira.delete_issue(issue_id)

        except Exception as e:
            yield self.create_text_message(f"Error deleting issue: {str(e)}")
            return

        yield self.create_json_message(
            {
                "result": "success",
            }
        )
