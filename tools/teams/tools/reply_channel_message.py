from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphError, require, resolve_graph_context, segment


class ReplyChannelMessageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            graph = resolve_graph_context(self.runtime.credentials)
            team_id, channel_id, message_id, message = require(
                tool_parameters, "team_id", "channel_id", "message_id", "message"
            )
            content_type = tool_parameters.get("content_type") or "html"
            if content_type not in ("html", "text"):
                content_type = "html"
            data = graph.request(
                "POST",
                f"/teams/{segment(team_id)}/channels/{segment(channel_id)}/messages/{segment(message_id)}/replies",
                json={"body": {"contentType": content_type, "content": message}},
            ).json()
        except GraphError as e:
            yield self.create_text_message(str(e))
            return

        yield self.create_text_message(f"Reply posted. Reply ID: {data.get('id')}")
        yield self.create_json_message(data)
