from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require
from tools.outputs import with_outputs


class ConvertTableToRangeTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            workbook_id, table = require(tool_parameters, "workbook_id", "table")
            ctx = context_for(self, tool_parameters)
            result = graph_request(ctx, "POST", f"{ctx.table(workbook_id, table)}/convertToRange").json()
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to convert the table: {e}")
            return
        address = result.get("address", "")
        self._out.update(address=address, success=True)
        yield self.create_text_message(f"Converted table '{table}' to a plain range ({address}); the data stays.")
