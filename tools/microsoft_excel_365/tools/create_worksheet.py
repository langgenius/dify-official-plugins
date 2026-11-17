from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require
from tools.outputs import with_outputs


class CreateWorksheetTool(Tool):
    """Add a worksheet to a workbook"""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            workbook_id, worksheet_name = require(tool_parameters, "workbook_id", "worksheet_name")
            ctx = context_for(self, tool_parameters)
            data = graph_request(
                ctx, "POST", f"{ctx.workbook(workbook_id)}/worksheets", json_body={"name": worksheet_name}
            ).json()
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to create worksheet: {e}")
            return

        worksheet = {
            "id": data.get("id", ""),
            "name": data.get("name", ""),
            "position": data.get("position", 0),
            "visibility": data.get("visibility", "Visible"),
        }
        self._out.update(worksheet_id=worksheet["id"], name=worksheet["name"], position=int(worksheet["position"] or 0), success=True)
        yield self.create_json_message({"workbook_id": workbook_id, "worksheet": worksheet, "status": "created"})
        yield self.create_text_message(f"Successfully created worksheet '{worksheet['name']}' at position {worksheet['position']}.")
