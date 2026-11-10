from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, get_all, list_dict
from tools.outputs import with_outputs


class GetTasksTool(Tool):
    """The user's task lists. (Named get_tasks for history: it has always returned the lists.)"""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            ctx = context_for(self, tool_parameters)
            lists = [list_dict(item) for item in get_all(ctx, ctx.lists(), {"$top": 99}, 999)]
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to get the task lists: {e}")
            return
        self._out.update(lists=lists, count=len(lists), success=True)
        yield self.create_json_message({"data": lists})
        yield self.create_text_message(str(lists))
