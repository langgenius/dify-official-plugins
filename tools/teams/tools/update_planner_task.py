from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphError, etag_of, require, resolve_graph_context, segment, to_graph_datetime


class UpdatePlannerTaskTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            graph = resolve_graph_context(self.runtime.credentials)
            (task_id,) = require(tool_parameters, "task_id")
            changes: dict[str, Any] = {}
            note = ""

            title = (tool_parameters.get("title") or "").strip()
            if title:
                changes["title"] = title
            bucket_id = (tool_parameters.get("bucket_id") or "").strip()
            if bucket_id:
                changes["bucketId"] = bucket_id
            percent = tool_parameters.get("percent_complete")
            if percent not in (None, ""):
                try:
                    percent = int(percent)
                except (TypeError, ValueError) as e:
                    raise GraphError("percent_complete must be a number from 0 to 100.") from e
                if not 0 <= percent <= 100:
                    raise GraphError("percent_complete must be a number from 0 to 100.")
                changes["percentComplete"] = percent
            due = (tool_parameters.get("due_datetime") or "").strip()
            if due:
                changes["dueDateTime"], assumed = to_graph_datetime(due, "due_datetime")
                if assumed:
                    note = " (the due date had no UTC offset and was taken as UTC)"
            if not changes:
                raise GraphError(
                    "Nothing to update: set at least one of title, bucket_id, percent_complete, due_datetime."
                )

            path = f"/planner/tasks/{segment(task_id)}"
            response = graph.request(
                "PATCH",
                path,
                json=changes,
                headers={"If-Match": etag_of(graph, path), "Prefer": "return=representation"},
            )
            task = response.json() if response.content else {"id": task_id, **changes}
        except GraphError as e:
            yield self.create_text_message(str(e))
            return

        yield self.create_text_message(f"Task updated{note}: {', '.join(changes)}.")
        yield self.create_json_message(task)
