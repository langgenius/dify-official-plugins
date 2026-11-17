from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require
from tools.outputs import with_outputs


class DeleteWorksheetTool(Tool):
    """Delete a worksheet from a workbook."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            workbook_id, worksheet_name = require(tool_parameters, "workbook_id", "worksheet_name")
            ctx = context_for(self, tool_parameters)
            graph_request(ctx, "DELETE", ctx.worksheet(workbook_id, worksheet_name))
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to delete the worksheet: {e}")
            return
        self._out.update(worksheet_name=worksheet_name, success=True)
        yield self.create_text_message(f"Deleted worksheet '{worksheet_name}'.")
