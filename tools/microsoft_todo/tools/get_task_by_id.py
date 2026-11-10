from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require, task_dict
from tools.outputs import with_outputs


class GetTaskByIdTool(Tool):
    """One task."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            task_id, list_id = require(tool_parameters, "task_id", "list_id")
            ctx = context_for(self, tool_parameters)
            task = task_dict(graph_request(ctx, "GET", ctx.task(list_id, task_id)).json())
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to get the task: {e}")
            return
        self._out.update(task, success=True)
        yield self.create_json_message(task)
        yield self.create_text_message(str(task))
