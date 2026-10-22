from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphError, require, resolve_graph_context, segment

_MAX_PAGES = 10  # safety cap when following @odata.nextLink


class ListPlannerTasksTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            graph = resolve_graph_context(self.runtime.credentials)
            (plan_id,) = require(tool_parameters, "plan_id")
            try:
                limit = min(max(int(tool_parameters.get("limit") or 50), 1), 200)
            except (TypeError, ValueError):
                limit = 50
            include_completed = tool_parameters.get("include_completed")
            include_completed = True if include_completed is None else bool(include_completed)

            tasks: list[dict[str, Any]] = []
            path = f"/planner/plans/{segment(plan_id)}/tasks"
            for _ in range(_MAX_PAGES):
                body = graph.request("GET", path).json()
                tasks.extend(body.get("value", []))
                next_link = body.get("@odata.nextLink") or ""
                # Only follow links back to the same Graph endpoint.
                if len(tasks) >= limit or not next_link.startswith(graph.api_base + "/"):
                    break
                path = next_link[len(graph.api_base):]
        except GraphError as e:
            yield self.create_text_message(str(e))
            return

        if not include_completed:
            tasks = [t for t in tasks if (t.get("percentComplete") or 0) < 100]
        result = [
            {
                "id": t.get("id"),
                "title": t.get("title"),
                "bucketId": t.get("bucketId"),
                "percentComplete": t.get("percentComplete"),
                "dueDateTime": t.get("dueDateTime"),
                "assigneeIds": list((t.get("assignments") or {}).keys()),
                "createdDateTime": t.get("createdDateTime"),
            }
            for t in tasks[:limit]
        ]
        yield self.create_text_message(f"Found {len(result)} task(s) in the plan.")
        yield self.create_json_message({"tasks": result})
