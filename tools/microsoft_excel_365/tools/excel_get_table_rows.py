from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.excel_tables import _LOOKUP_MAX_ROWS, table_header, table_rows
from tools.graph_client import GraphAuthError, context_for, require
from tools.outputs import with_outputs
from tools.sheet_rows import as_records


class GetTableRowsTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            limit = max(1, min(int(tool_parameters.get("limit") or 100), _LOOKUP_MAX_ROWS))
        except (TypeError, ValueError):
            limit = 100
        try:
            workbook_id, table = require(tool_parameters, "workbook_id", "table")
            ctx = context_for(self, tool_parameters)
            header = table_header(ctx, workbook_id, table)
            rows, has_more = table_rows(ctx, workbook_id, table, limit)
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to get the table's rows: {e}")
            return
        records = as_records(header, rows)
        self._out.update(rows=records, count=len(records), has_more=has_more, success=True)
        more = " (more rows exist; raise the limit)" if has_more else ""
        yield self.create_text_message(f"{len(records)} row(s) from table '{table}'{more}.")
        yield self.create_json_message({"columns": header, "rows": records, "count": len(records), "has_more": has_more})
