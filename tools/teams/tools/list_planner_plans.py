from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphError, require, resolve_graph_context, segment


class ListPlannerPlansTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            graph = resolve_graph_context(self.runtime.credentials)
            (team_id,) = require(tool_parameters, "team_id")
            data = graph.request("GET", f"/groups/{segment(team_id)}/planner/plans").json()
        except GraphError as e:
            yield self.create_text_message(str(e))
            return

        plans = [
            {"id": p.get("id"), "title": p.get("title"), "createdDateTime": p.get("createdDateTime")}
            for p in data.get("value", [])
        ]
        yield self.create_text_message(
            f"Found {len(plans)} plan(s) in the team." if plans else "This team has no Planner plans."
        )
        yield self.create_json_message({"plans": plans})
