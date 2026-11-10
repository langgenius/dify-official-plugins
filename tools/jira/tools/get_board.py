from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import connect


class ListBoardTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        jira = yield from connect(self)
        if jira is None:
            return

        board_id = tool_parameters.get("board_id")

        board = jira.get_agile_board(board_id)

        yield self.create_json_message(board)
