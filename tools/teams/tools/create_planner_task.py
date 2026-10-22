from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphError, require, resolve_graph_context, split_list, to_graph_datetime


class CreatePlannerTaskTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            graph = resolve_graph_context(self.runtime.credentials)
            plan_id, title = require(tool_parameters, "plan_id", "title")
            body: dict[str, Any] = {"planId": plan_id, "title": title}

            bucket_id = (tool_parameters.get("bucket_id") or "").strip()
            if bucket_id:
                body["bucketId"] = bucket_id

            note = ""
            due = (tool_parameters.get("due_datetime") or "").strip()
            if due:
                body["dueDateTime"], assumed = to_graph_datetime(due, "due_datetime")
                if assumed:
                    note = " (the due date had no UTC offset and was taken as UTC)"

            assignees = split_list(tool_parameters.get("assignee_ids"))
            if assignees:
                if "me" in assignees:
                    me = graph.request("GET", "/me", params={"$select": "id"}).json()["id"]
                    assignees = [me if a == "me" else a for a in assignees]
                body["assignments"] = {
                    user_id: {"@odata.type": "#microsoft.graph.plannerAssignment", "orderHint": " !"}
                    for user_id in assignees
                }
            data = graph.request("POST", "/planner/tasks", json=body).json()
        except GraphError as e:
            yield self.create_text_message(str(e))
            return

        yield self.create_text_message(f"Task created{note}. Task ID: {data.get('id')}")
        yield self.create_json_message(data)
