from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphError, etag_of, require, resolve_graph_context, segment


class DeletePlannerTaskTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            graph = resolve_graph_context(self.runtime.credentials)
            (task_id,) = require(tool_parameters, "task_id")
            path = f"/planner/tasks/{segment(task_id)}"
            graph.request("DELETE", path, headers={"If-Match": etag_of(graph, path)})
        except GraphError as e:
            yield self.create_text_message(str(e))
            return

        yield self.create_text_message("Task deleted.")
        yield self.create_json_message({"status": "deleted", "task_id": task_id})
