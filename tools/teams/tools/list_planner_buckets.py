from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphError, require, resolve_graph_context, segment


class ListPlannerBucketsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            graph = resolve_graph_context(self.runtime.credentials)
            (plan_id,) = require(tool_parameters, "plan_id")
            data = graph.request("GET", f"/planner/plans/{segment(plan_id)}/buckets").json()
        except GraphError as e:
            yield self.create_text_message(str(e))
            return

        buckets = [{"id": b.get("id"), "name": b.get("name")} for b in data.get("value", [])]
        yield self.create_text_message(f"Found {len(buckets)} bucket(s) in the plan.")
        yield self.create_json_message({"buckets": buckets})
