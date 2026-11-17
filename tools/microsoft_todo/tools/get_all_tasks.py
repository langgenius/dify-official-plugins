from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.get_tasks_by_list_id import task_filter, task_limit
from tools.graph_client import GraphAuthError, context_for, get_all, task_dict
from tools.outputs import with_outputs


class GetAllTasksTool(Tool):
    """Tasks of every list, not completed ones by default."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            limit = task_limit(tool_parameters)
            status = task_filter(tool_parameters)
            ctx = context_for(self, tool_parameters)
            tasks: list[dict[str, Any]] = []
            for task_list in get_all(ctx, ctx.lists(), {"$top": 99}, 999):
                params: dict[str, Any] = {"$top": min(limit, 100)}
                if status:
                    params["$filter"] = status
                for task in get_all(ctx, ctx.tasks(task_list["id"]), params, limit):
                    tasks.append(dict(task_dict(task), list_id=task_list["id"], list_name=task_list.get("displayName", "")))
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to get the tasks: {e}")
            return
        self._out.update(tasks=tasks, count=len(tasks), success=True)
        yield self.create_json_message({"data": tasks})
        yield self.create_text_message(str(tasks))
