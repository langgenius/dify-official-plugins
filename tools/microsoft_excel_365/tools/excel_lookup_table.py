from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.excel_tables import _LOOKUP_MAX_ROWS, table_header, table_rows
from tools.graph_client import GraphAuthError, context_for, require
from tools.outputs import with_outputs
from tools.sheet_rows import as_records


class LookupTableTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            workbook_id, table, column, value = require(tool_parameters, "workbook_id", "table", "column", "value")
            ctx = context_for(self, tool_parameters)
            header = table_header(ctx, workbook_id, table)
            if column not in header:
                raise GraphAuthError(f"'{column}' is not a column of the table. Columns: {', '.join(header)}.")
            rows, truncated = table_rows(ctx, workbook_id, table, _LOOKUP_MAX_ROWS)
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to look up the table: {e}")
            return
        at = header.index(column)
        # Text comparison, so 42 matches "42" (Excel returns numbers for numeric cells).
        matches = as_records(header, [r for r in rows if at < len(r) and str(r[at]).strip() == value.strip()])
        if tool_parameters.get("return_all_matches") is False:
            matches = matches[:1]
        self._out.update(rows=matches, count=len(matches), success=True)
        note = f" (only the first {_LOOKUP_MAX_ROWS} rows were searched)" if truncated else ""
        yield self.create_text_message(f"{len(matches)} row(s) where {column} = {value}{note}.")
        yield self.create_json_message({"rows": matches, "count": len(matches)})
