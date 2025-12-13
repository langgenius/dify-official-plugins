from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import auth


class ListBoardTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        jira = auth(self.runtime.credentials)

        board_id = tool_parameters.get("board_id")

        board = jira.get_agile_board(board_id)

        yield self.create_json_message(board)
