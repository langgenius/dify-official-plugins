from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require
from tools.outputs import with_outputs


class ListWorksheetsTool(Tool):
    """List the worksheets of a workbook"""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            (workbook_id,) = require(tool_parameters, "workbook_id")
            ctx = context_for(self, tool_parameters)
            data = graph_request(ctx, "GET", f"{ctx.workbook(workbook_id)}/worksheets").json()
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to list worksheets: {e}")
            return

        worksheets = sorted(
            (
                {
                    "id": sheet.get("id", ""),
                    "name": sheet.get("name", ""),
                    "position": sheet.get("position", 0),
                    "visibility": sheet.get("visibility", "Visible"),
                }
                for sheet in data.get("value", [])
            ),
            key=lambda sheet: sheet["position"],
        )
        self._out.update(worksheets=worksheets, count=len(worksheets), success=True)
        if not worksheets:
            yield self.create_text_message("No worksheets found in the workbook.")
            return
        yield self.create_json_message({"workbook_id": workbook_id, "worksheets": worksheets, "count": len(worksheets)})
        summary = f"Found {len(worksheets)} worksheet(s) in the workbook:\n"
        for ws in worksheets:
            hidden = "" if ws["visibility"] == "Visible" else f" ({ws['visibility']})"
            summary += f"- {ws['name']}{hidden}\n"
        yield self.create_text_message(summary)
