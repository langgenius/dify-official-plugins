from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, column_letter, context_for, graph_request, require, top_left
from tools.outputs import with_outputs


class SearchWorksheetDataTool(Tool):
    """Find cells equal to a value in a range"""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        search_range = str(tool_parameters.get("range") or "A1:Z1000").strip()
        try:
            workbook_id, worksheet_name, search_value = require(tool_parameters, "workbook_id", "worksheet_name", "search_value")
            ctx = context_for(self, tool_parameters)
            data = graph_request(ctx, "GET", ctx.range(workbook_id, worksheet_name, search_range)).json()
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to search worksheet data: {e}")
            return

        # Cell references are relative to where the range starts, not to A1.
        first_col, first_row = top_left(data.get("address") or search_range)
        matches = []
        for row_idx, row in enumerate(data.get("values", [])):
            for col_idx, cell_value in enumerate(row):
                if str(cell_value).lower() == search_value.lower():
                    col = column_letter(first_col + col_idx)
                    row_number = first_row + row_idx
                    matches.append({"cell": f"{col}{row_number}", "value": cell_value, "row": row_number, "column": col})

        self._out.update(
            matches=[{**m, "value": str(m["value"])} for m in matches], match_count=len(matches), success=True
        )
        if not matches:
            yield self.create_text_message(f"No matches found for '{search_value}' in the specified range.")
            return
        yield self.create_json_message(
            {"workbook_id": workbook_id, "worksheet": worksheet_name, "search_value": search_value,
             "matches": matches, "match_count": len(matches)}
        )
        summary = f"Found {len(matches)} match(es) for '{search_value}' in worksheet '{worksheet_name}':\n\n"
        for match in matches[:10]:
            summary += f"- Cell {match['cell']}: {match['value']}\n"
        if len(matches) > 10:
            summary += f"\n... and {len(matches) - 10} more matches"
        yield self.create_text_message(summary)
