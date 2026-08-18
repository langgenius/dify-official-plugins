from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_api import SlackApiError, SlackClient


class ListChannelsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("Slack Access Token is required.")
            return

        types = (tool_parameters.get("types") or "").strip() or None
        cursor = (tool_parameters.get("cursor") or "").strip() or None
        try:
            limit = int(tool_parameters.get("limit") or 100)
        except (TypeError, ValueError):
            limit = 100
        limit = max(1, min(limit, 1000))

        try:
            client = SlackClient(token)
            resp = client.api_call(
                "conversations.list",
                {"types": types, "limit": limit, "cursor": cursor},
            )
        except SlackApiError as e:
            yield self.create_text_message(f"Failed to list channels: {e.slack_error}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        channels = resp.get("channels", [])
        summary_lines = [
            f"- {c.get('name', '(no name)')} (id: {c.get('id')})" for c in channels
        ]
        header = f"Found {len(channels)} channel(s):"
        yield self.create_text_message("\n".join([header, *summary_lines]))
        yield self.create_json_message(resp)
