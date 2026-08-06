from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_api import SlackApiError, SlackClient


class GetChannelHistoryTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("Slack Access Token is required.")
            return

        channel = (tool_parameters.get("channel") or "").strip()
        if not channel:
            yield self.create_text_message("The 'channel' parameter is required.")
            return

        oldest = (tool_parameters.get("oldest") or "").strip() or None
        latest = (tool_parameters.get("latest") or "").strip() or None
        try:
            limit = int(tool_parameters.get("limit") or 20)
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(limit, 1000))

        try:
            client = SlackClient(token)
            resp = client.api_call(
                "conversations.history",
                {"channel": channel, "limit": limit, "oldest": oldest, "latest": latest},
            )
        except SlackApiError as e:
            yield self.create_text_message(f"Failed to get channel history: {e.slack_error}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        messages = resp.get("messages", [])
        yield self.create_text_message(f"Retrieved {len(messages)} message(s) from {channel}.")
        yield self.create_json_message(resp)
