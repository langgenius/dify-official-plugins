from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, get_all, require, task_dict
from tools.outputs import with_outputs

# Before 1.0.0 the tool returned only tasks that are not completed; that stays the default.
STATUS_FILTERS = {"not_completed": "status ne 'completed'", "completed": "status eq 'completed'", "all": None}


def task_filter(tool_parameters: dict[str, Any]) -> str | None:
    name = str(tool_parameters.get("status_filter") or "not_completed").strip()
    if name not in STATUS_FILTERS:
        raise GraphAuthError(f"status_filter must be one of: {', '.join(STATUS_FILTERS)}.")
    return STATUS_FILTERS[name]


def task_limit(tool_parameters: dict[str, Any]) -> int:
    try:
        return max(1, min(int(tool_parameters.get("limit") or 1000), 1000))
    except (TypeError, ValueError) as e:
        raise GraphAuthError("limit must be a number from 1 to 1000.") from e


class GetTasksByListIdTool(Tool):
    """Tasks of one list, not completed ones by default."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            (list_id,) = require(tool_parameters, "list_id")
            limit = task_limit(tool_parameters)
            params: dict[str, Any] = {"$top": min(limit, 100)}
            status = task_filter(tool_parameters)
            if status:
                params["$filter"] = status
            ctx = context_for(self, tool_parameters)
            tasks = [task_dict(t) for t in get_all(ctx, ctx.tasks(list_id), params, limit)]
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to get the tasks: {e}")
            return
        self._out.update(tasks=tasks, count=len(tasks), success=True)
        yield self.create_json_message({"data": tasks})
        yield self.create_text_message(str(tasks))
