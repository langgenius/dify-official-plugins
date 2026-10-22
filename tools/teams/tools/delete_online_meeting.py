from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphError, require, resolve_graph_context, segment


class DeleteOnlineMeetingTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            graph = resolve_graph_context(self.runtime.credentials)
            (meeting_id,) = require(tool_parameters, "meeting_id")
            graph.request("DELETE", f"/me/onlineMeetings/{segment(meeting_id)}")
        except GraphError as e:
            yield self.create_text_message(str(e))
            return

        yield self.create_text_message("Online meeting deleted.")
        yield self.create_json_message({"status": "deleted", "meeting_id": meeting_id})
