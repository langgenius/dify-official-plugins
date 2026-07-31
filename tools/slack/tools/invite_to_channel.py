from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_client import SlackClient, SlackConfigError
from tool_utils import slack_result


class InviteToChannelTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = SlackClient(self.runtime.credentials)
        except SlackConfigError as e:
            yield self.create_text_message(str(e))
            return

        channel = (tool_parameters.get("channel") or "").strip()
        users = (tool_parameters.get("users") or "").strip()
        if not channel or not users:
            yield self.create_text_message("Channel and Users are required.")
            return
        users = ",".join(u.strip() for u in users.split(",") if u.strip())

        try:
            response = client.call(
                "conversations.invite",
                "POST",
                json_body={"channel": channel, "users": users},
            )
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Request failed: {e}")
            return

        ok, data, error = slack_result(response)
        yield self.create_json_message(data)
        if not ok:
            yield self.create_text_message(f"Slack error: {error}")
            return
        yield self.create_text_message(f"Invited user(s) to {channel}.")
