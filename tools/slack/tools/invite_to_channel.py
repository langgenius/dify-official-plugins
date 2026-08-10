from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_api import SlackApiError, SlackClient


class InviteToChannelTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("Slack Access Token is required.")
            return

        channel = (tool_parameters.get("channel") or "").strip()
        users_raw = (tool_parameters.get("users") or "").strip()
        if not channel or not users_raw:
            yield self.create_text_message("Both 'channel' and 'users' are required.")
            return

        users = ",".join(u.strip() for u in users_raw.split(",") if u.strip())
        if not users:
            yield self.create_text_message("No valid user IDs were provided.")
            return

        try:
            client = SlackClient(token)
            resp = client.api_call(
                "conversations.invite", {"channel": channel, "users": users}
            )
        except SlackApiError as e:
            yield self.create_text_message(f"Failed to invite users: {e.slack_error}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        ch = resp.get("channel", {})
        yield self.create_text_message(
            f"Invited users to {ch.get('name', channel)}."
        )
        yield self.create_json_message(resp)
