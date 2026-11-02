from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, list_dict, require
from tools.outputs import with_outputs


class GetListByIdTool(Tool):
    """One task list."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            (list_id,) = require(tool_parameters, "list_id")
            ctx = context_for(self, tool_parameters)
            task_list = list_dict(graph_request(ctx, "GET", ctx.task_list(list_id)).json())
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to get the list: {e}")
            return
        self._out.update(list_id=task_list["list_id"], display_name=task_list["display_name"], success=True)
        yield self.create_json_message(task_list)
        yield self.create_text_message(str(task_list))
