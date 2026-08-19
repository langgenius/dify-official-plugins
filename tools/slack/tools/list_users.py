from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_api import SlackApiError, SlackClient


class ListUsersTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("Slack Access Token is required.")
            return

        cursor = (tool_parameters.get("cursor") or "").strip() or None
        try:
            limit = int(tool_parameters.get("limit") or 100)
        except (TypeError, ValueError):
            limit = 100
        limit = max(1, min(limit, 1000))

        try:
            client = SlackClient(token)
            resp = client.api_call("users.list", {"limit": limit, "cursor": cursor})
        except SlackApiError as e:
            yield self.create_text_message(f"Failed to list users: {e.slack_error}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        members = resp.get("members", [])
        summary_lines = [
            f"- {m.get('name')} (id: {m.get('id')}, real_name: {m.get('real_name', '')})"
            for m in members
        ]
        yield self.create_text_message(
            "\n".join([f"Found {len(members)} user(s):", *summary_lines])
        )
        yield self.create_json_message(resp)
