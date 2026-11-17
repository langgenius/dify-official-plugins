from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require
from tools.outputs import with_outputs


class DeleteTaskTool(Tool):
    """Delete a task."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            list_id, task_id = require(tool_parameters, "list_id", "task_id")
            ctx = context_for(self, tool_parameters)
            graph_request(ctx, "DELETE", ctx.task(list_id, task_id))
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to delete the task: {e}")
            return
        self._out.update(task_id=task_id, success=True)
        yield self.create_text_message(f"Deleted task {task_id}.")
