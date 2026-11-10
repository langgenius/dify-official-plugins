from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require
from tools.outputs import with_outputs


class ReadWorksheetDataTool(Tool):
    """Read cell values from a range"""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        range_address = str(tool_parameters.get("range") or "A1:Z100").strip()
        try:
            workbook_id, worksheet_name = require(tool_parameters, "workbook_id", "worksheet_name")
            ctx = context_for(self, tool_parameters)
            data = graph_request(ctx, "GET", ctx.range(workbook_id, worksheet_name, range_address)).json()
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to read worksheet data: {e}")
            return

        values = data.get("values", [])
        row_count = data.get("rowCount", 0)
        column_count = data.get("columnCount", 0)
        address = data.get("address", "")
        self._out.update(values=values, address=address, row_count=int(row_count or 0), column_count=int(column_count or 0), success=True)
        yield self.create_json_message(
            {"workbook_id": workbook_id, "worksheet": worksheet_name, "range": address,
             "row_count": row_count, "column_count": column_count, "values": values}
        )
        if not values:
            yield self.create_text_message(f"The range {address} is empty.")
            return
        summary = f"Successfully read {row_count} rows × {column_count} columns from '{worksheet_name}' ({address})\n\n"
        preview_rows = min(5, len(values))
        summary += "Preview (first 5 rows):\n"
        for i in range(preview_rows):
            row = values[i]
            summary += f"Row {i + 1}: {row[:5] if len(row) > 5 else row}...\n"
        if row_count > preview_rows:
            summary += f"\n... and {row_count - preview_rows} more rows"
        yield self.create_text_message(summary)
