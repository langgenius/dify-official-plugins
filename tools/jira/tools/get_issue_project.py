from collections.abc import Generator
from typing import Any

from atlassian.jira import Jira
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from .util import simplify_issue


class GetIssueProjectTool(Tool):
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

        try:
            issues = jira.jql(f"project = {project_key} ORDER BY issuekey")

            simplified_issues = [simplify_issue(issue) for issue in issues["issues"]]

            yield self.create_json_message({"issues": simplified_issues})

        except Exception as e:
            yield self.create_json_message(
                {
                    "error": f"Error occurred while fetching issues for project {project_key}: {str(e)}",
                }
            )
