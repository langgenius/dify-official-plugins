from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, get_all, require, resource_dict
from tools.outputs import with_outputs


class ListLinkedResourcesTool(Tool):
    """A task's linked resources: links to the item in another app the task came from."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            list_id, task_id = require(tool_parameters, "list_id", "task_id")
            try:
                limit = max(1, min(int(tool_parameters.get("limit") or 50), 1000))
            except (TypeError, ValueError) as e:
                raise GraphAuthError("limit must be a number from 1 to 1000.") from e
            ctx = context_for(self, tool_parameters)
            resources = [resource_dict(r) for r in get_all(ctx, ctx.linked_resources(list_id, task_id), {"$top": min(limit, 100)}, limit)]
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to get the linked resources: {e}")
            return
        self._out.update(linked_resources=resources, count=len(resources), success=True)
        yield self.create_json_message({"data": resources})
        yield self.create_text_message(str(resources) if resources else "The task has no linked resources.")
