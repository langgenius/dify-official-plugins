from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphError, message_vars, resolve_graph_context
from tools.outputs import with_outputs


class ListChannelMessagesTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            graph = resolve_graph_context(self.runtime.credentials)
        except GraphError as e:
            yield self.create_text_message(str(e))
            return
        access_token = graph.access_token

        team_id = tool_parameters.get("team_id", "")
        channel_id = tool_parameters.get("channel_id", "")

        if not team_id:
            yield self.create_text_message("team_id is required.")
            return
        if not channel_id:
            yield self.create_text_message("channel_id is required.")
            return

        try:
            top = int(tool_parameters.get("top") or 20)
        except (TypeError, ValueError):
            top = 20

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        url = (
            f"{graph.api_base}/teams/{team_id}"
            f"/channels/{channel_id}/messages"
        )
        params = {"$top": top}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
            return

        if response.status_code < 200 or response.status_code >= 300:
            yield self.create_text_message(
                f"API error {response.status_code}: {response.text}"
            )
            return

        data = response.json()
        messages = [
            {
                "id": msg.get("id"),
                "from": msg.get("from"),
                "content": (msg.get("body") or {}).get("content"),
                "createdDateTime": msg.get("createdDateTime"),
            }
            for msg in data.get("value", [])
        ]

        if not messages:
            yield self.create_text_message("No messages found in this channel.")
        else:
            yield self.create_text_message(
                f"Found {len(messages)} message(s) in the channel."
            )

        self._out.update(messages=[message_vars(m) for m in data.get("value", [])], count=len(messages), success=True)
        yield self.create_json_message({"messages": messages})
