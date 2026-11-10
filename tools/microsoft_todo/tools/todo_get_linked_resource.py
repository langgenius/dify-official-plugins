from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require, resource_dict
from tools.outputs import with_outputs


class GetLinkedResourceTool(Tool):
    """One linked resource of a task."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            list_id, task_id, resource_id = require(tool_parameters, "list_id", "task_id", "linked_resource_id")
            ctx = context_for(self, tool_parameters)
            resource = resource_dict(graph_request(ctx, "GET", ctx.linked_resource(list_id, task_id, resource_id)).json())
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to get the linked resource: {e}")
            return
        self._out.update(resource, success=True)
        yield self.create_json_message(resource)
        yield self.create_text_message(str(resource))
