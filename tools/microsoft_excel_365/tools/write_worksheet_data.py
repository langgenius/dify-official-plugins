from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, parse_rows, require
from tools.outputs import with_outputs


class WriteWorksheetDataTool(Tool):
    """Write values into a range"""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            workbook_id, worksheet_name, range_address = require(tool_parameters, "workbook_id", "worksheet_name", "range")
            values = parse_rows(tool_parameters.get("values"))
            ctx = context_for(self, tool_parameters)
            data = graph_request(
                ctx, "PATCH", ctx.range(workbook_id, worksheet_name, range_address), json_body={"values": values}
            ).json()
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to write worksheet data: {e}")
            return

        row_count = data.get("rowCount", 0)
        column_count = data.get("columnCount", 0)
        address = data.get("address", "")
        self._out.update(address=address, rows_written=int(row_count or 0), columns_written=int(column_count or 0), success=True)
        yield self.create_json_message(
            {"workbook_id": workbook_id, "worksheet": worksheet_name, "range": address,
             "rows_written": row_count, "columns_written": column_count, "values": values}
        )
        summary = f"Successfully wrote {row_count} rows × {column_count} columns to '{worksheet_name}' ({address})\n\n"
        preview_rows = min(3, len(values))
        summary += "Data written:\n"
        for i in range(preview_rows):
            row = values[i]
            summary += f"Row {i + 1}: {row[:5] if len(row) > 5 else row}\n"
        if len(values) > preview_rows:
            summary += f"... and {len(values) - preview_rows} more rows"
        yield self.create_text_message(summary)
