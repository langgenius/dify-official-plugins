from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require
from tools.outputs import with_outputs


class ClearWorksheetDataTool(Tool):
    """Clear the contents of a range"""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            workbook_id, worksheet_name, range_address = require(tool_parameters, "workbook_id", "worksheet_name", "range")
            ctx = context_for(self, tool_parameters)
            # Contents only: formatting stays.
            graph_request(
                ctx, "POST", f"{ctx.range(workbook_id, worksheet_name, range_address)}/clear", json_body={"applyTo": "Contents"}
            )
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to clear worksheet data: {e}")
            return

        self._out.update(range_cleared=range_address, success=True)
        yield self.create_json_message(
            {"workbook_id": workbook_id, "worksheet": worksheet_name, "range_cleared": range_address, "status": "success"}
        )
        yield self.create_text_message(
            f"Successfully cleared data from range '{range_address}' in worksheet '{worksheet_name}'."
        )
