from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import auth


class ListIssueTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        jira = auth(self.runtime.credentials)

        board_id = tool_parameters.get("board_id")

        try:

            yield self.create_json_message(
                {
                    "issues": jira.get_issues_for_board(
                        board_id=board_id,
                        start=0,
                        limit=50,  # Note: limit is 50 by default
                        jql=None,
                    )
                }
            )

        except Exception as e:
            yield self.create_json_message(
                {
                    "error": f"Error occurred while fetching issues for board with ID {board_id}: {str(e)}",
                }
            )
