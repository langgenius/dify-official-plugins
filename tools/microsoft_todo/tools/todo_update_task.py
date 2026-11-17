from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, require, task_dict, task_fields
from tools.outputs import with_outputs


class UpdateTaskTool(Tool):
    """Change a task's title, notes, due date, reminder, importance or status."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            list_id, task_id = require(tool_parameters, "list_id", "task_id")
            body = task_fields(tool_parameters, for_update=True)
            if not body:
                raise GraphAuthError("Give at least one field to change (title, body_text, due_date, reminder_datetime, importance, status).")
            ctx = context_for(self, tool_parameters)
            task = task_dict(graph_request(ctx, "PATCH", ctx.task(list_id, task_id), json_body=body).json())
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to update the task: {e}")
            return
        self._out.update(task, success=True)
        yield self.create_json_message(task)
        yield self.create_text_message(f"Updated task '{task['title']}' ({', '.join(sorted(body))}).")
