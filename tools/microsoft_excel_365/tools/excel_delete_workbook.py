from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require, segment
from tools.outputs import with_outputs


class DeleteWorkbookTool(Tool):
    """Delete a workbook file; it goes to the drive's recycle bin."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            (workbook_id,) = require(tool_parameters, "workbook_id")
            ctx = context_for(self, tool_parameters)
            graph_request(ctx, "DELETE", f"{ctx.drive_base}/items/{segment(workbook_id)}")
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to delete the workbook: {e}")
            return
        self._out.update(workbook_id=workbook_id, success=True)
        yield self.create_text_message(f"Deleted workbook {workbook_id} (it is in the recycle bin).")
