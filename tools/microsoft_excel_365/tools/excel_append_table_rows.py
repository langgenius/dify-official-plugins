from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.excel_tables import table_header
from tools.graph_client import GraphAuthError, context_for, graph_request, require
from tools.outputs import with_outputs
from tools.sheet_rows import parse_records, rows_for_header


class AppendTableRowsTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            workbook_id, table = require(tool_parameters, "workbook_id", "table")
            records = parse_records(tool_parameters.get("rows"))
            ctx = context_for(self, tool_parameters)
            header = table_header(ctx, workbook_id, table)
            rows = rows_for_header(records, header)
            graph_request(ctx, "POST", f"{ctx.table(workbook_id, table)}/rows", json_body={"index": None, "values": rows})
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to append rows to the table: {e}")
            return
        self._out.update(rows_appended=len(rows), success=True)
        yield self.create_text_message(f"Appended {len(rows)} row(s) to table '{table}'.")
