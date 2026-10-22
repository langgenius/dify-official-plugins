from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphError, require, resolve_graph_context, segment


class ListChannelMessageRepliesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            graph = resolve_graph_context(self.runtime.credentials)
            team_id, channel_id, message_id = require(tool_parameters, "team_id", "channel_id", "message_id")
            try:
                top = min(max(int(tool_parameters.get("top") or 20), 1), 50)
            except (TypeError, ValueError):
                top = 20
            data = graph.request(
                "GET",
                f"/teams/{segment(team_id)}/channels/{segment(channel_id)}/messages/{segment(message_id)}/replies",
                params={"$top": top},
            ).json()
        except GraphError as e:
            yield self.create_text_message(str(e))
            return

        replies = [
            {
                "id": msg.get("id"),
                "from": msg.get("from"),
                "content": (msg.get("body") or {}).get("content"),
                "createdDateTime": msg.get("createdDateTime"),
            }
            for msg in data.get("value", [])
        ]
        yield self.create_text_message(f"Found {len(replies)} reply(s)." if replies else "No replies found.")
        yield self.create_json_message({"replies": replies})
