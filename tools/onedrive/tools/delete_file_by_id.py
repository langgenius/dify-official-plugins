from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.outputs import with_outputs
from tools.graph_client import graph_request, GraphAuthError, resolve_graph_context, segment


class DeleteFileByIdTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        file_id = tool_parameters.get("file_id")
        if not file_id:
            yield self.create_text_message("File ID is required.")
            yield self.create_json_message({"error": "File ID is required."})
            return
        try:
            graph = resolve_graph_context(self.runtime.credentials, tool_parameters.get("drive_user"))
            graph_request(graph, "DELETE", f"{graph.drive_base}/items/{segment(file_id)}")
            self._out.update(file_id=str(file_id), success=True)
            yield self.create_json_message({"success": True, "file_id": file_id})
        except GraphAuthError as e:
            yield self.create_json_message({"error": str(e)})
            yield self.create_text_message(f"Error deleting file: {e}")
