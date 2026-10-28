from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphError, meeting_vars, require, resolve_graph_context, segment
from tools.outputs import with_outputs


class GetOnlineMeetingTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            graph = resolve_graph_context(self.runtime.credentials)
            (meeting_id,) = require(tool_parameters, "meeting_id")
            data = graph.request("GET", f"/me/onlineMeetings/{segment(meeting_id)}").json()
        except GraphError as e:
            yield self.create_text_message(str(e))
            return

        yield self.create_text_message(
            f"{data.get('subject') or 'Online meeting'}: {data.get('startDateTime')} - {data.get('endDateTime')}. "
            f"Join URL: {data.get('joinWebUrl')}"
        )
        self._out.update(**meeting_vars(data), success=True)
        yield self.create_json_message(data)
