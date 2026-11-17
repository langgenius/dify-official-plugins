from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.excel_tables import table_header
from tools.graph_client import GraphAuthError, context_for, require
from tools.outputs import with_outputs


class GetTableColumnsTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            workbook_id, table = require(tool_parameters, "workbook_id", "table")
            ctx = context_for(self, tool_parameters)
            columns = table_header(ctx, workbook_id, table)
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to get the table's columns: {e}")
            return
        self._out.update(columns=columns, count=len(columns), success=True)
        yield self.create_text_message(f"Table '{table}' has {len(columns)} column(s): {', '.join(columns)}")
        yield self.create_json_message({"columns": columns, "count": len(columns)})
