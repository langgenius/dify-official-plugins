from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import connect


class ListIssueTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        jira = yield from connect(self)
        if jira is None:
            return

        issue_key = tool_parameters.get("issue_key")

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
