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

        board_id = tool_parameters.get("board_id")

        jira = Jira(
            url=jira_url,
            username=username,
            password=api_token,
        )

        board = jira.get_agile_board(board_id)

        yield self.create_json_message(board)
