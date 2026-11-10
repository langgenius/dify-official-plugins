from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require
from tools.outputs import with_outputs


class DeleteListTool(Tool):
    """Delete a task list and its tasks."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            (list_id,) = require(tool_parameters, "list_id")
            ctx = context_for(self, tool_parameters)
            graph_request(ctx, "DELETE", ctx.task_list(list_id))
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to delete the list: {e}")
            return
        self._out.update(list_id=list_id, success=True)
        yield self.create_text_message(f"Deleted list {list_id} and its tasks.")
