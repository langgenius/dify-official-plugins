from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_api import SlackApiError, SlackClient


class GetThreadRepliesTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("Slack Access Token is required.")
            return

        channel = (tool_parameters.get("channel") or "").strip()
        ts = (tool_parameters.get("ts") or "").strip()
        if not channel or not ts:
            yield self.create_text_message("Both 'channel' and 'ts' are required.")
            return

        try:
            limit = int(tool_parameters.get("limit") or 100)
        except (TypeError, ValueError):
            limit = 100
        limit = max(1, min(limit, 1000))

        try:
            client = SlackClient(token)
            resp = client.api_call(
                "conversations.replies",
                {"channel": channel, "ts": ts, "limit": limit},
            )
        except SlackApiError as e:
            yield self.create_text_message(f"Failed to get thread replies: {e.slack_error}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        messages = resp.get("messages", [])
        yield self.create_text_message(
            f"Retrieved {len(messages)} message(s) in thread {ts}."
        )
        yield self.create_json_message(resp)
