from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require
from tools.outputs import with_outputs


class DeleteLinkedResourceTool(Tool):
    """Remove a linked resource from a task."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            list_id, task_id, resource_id = require(tool_parameters, "list_id", "task_id", "linked_resource_id")
            ctx = context_for(self, tool_parameters)
            graph_request(ctx, "DELETE", ctx.linked_resource(list_id, task_id, resource_id))
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to delete the linked resource: {e}")
            return
        self._out.update(linked_resource_id=resource_id, success=True)
        yield self.create_text_message(f"Removed linked resource {resource_id} from the task.")
