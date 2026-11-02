from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require
from tools.outputs import with_outputs


class DeleteTableTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            workbook_id, table = require(tool_parameters, "workbook_id", "table")
            ctx = context_for(self, tool_parameters)
            graph_request(ctx, "DELETE", ctx.table(workbook_id, table))
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to delete the table: {e}")
            return
        self._out.update(table=table, success=True)
        yield self.create_text_message(f"Deleted table '{table}' and its data.")
