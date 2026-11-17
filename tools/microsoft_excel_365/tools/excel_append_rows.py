from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, parse_rows, require
from tools.outputs import with_outputs
from tools.sheet_rows import UsedRange, parse_records, rows_for_header


class AppendRowsTool(Tool):
    """
    Add rows below the data on a worksheet. Rows are objects keyed
    by the header row, or lists of cell values. On an empty sheet, objects also write the header.
    """

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            workbook_id, worksheet_name = require(tool_parameters, "workbook_id", "worksheet_name")
            records = parse_records(tool_parameters.get("rows"))
            ctx = context_for(self, tool_parameters)
            used = UsedRange(ctx, workbook_id, worksheet_name)
            if isinstance(records[0], dict):
                if used.empty:
                    header = list(dict.fromkeys(str(k) for row in records for k in row))
                    rows = [header] + rows_for_header(records, header)
                else:
                    rows = rows_for_header(records, [str(h) for h in used.header])
            else:
                rows = parse_rows(records, "rows")
            start = used.next_row()
            address = used.address(start, len(rows[0]), len(rows))
            data = graph_request(ctx, "PATCH", ctx.range(workbook_id, worksheet_name, address), json_body={"values": rows}).json()
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to append rows: {e}")
            return

        written = data.get("address") or address
        self._out.update(address=written, rows_appended=len(rows), success=True)
        yield self.create_text_message(f"Appended {len(rows)} row(s) to '{worksheet_name}' at {written}.")
        yield self.create_json_message({"workbook_id": workbook_id, "worksheet": worksheet_name, "address": written, "rows_appended": len(rows)})
