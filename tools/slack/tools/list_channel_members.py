from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_client import SlackClient, SlackConfigError
from tool_utils import slack_result


class ListChannelMembersTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = SlackClient(self.runtime.credentials)
        except SlackConfigError as e:
            yield self.create_text_message(str(e))
            return

        channel = (tool_parameters.get("channel") or "").strip()
        if not channel:
            yield self.create_text_message("Channel is required.")
            return

        params: dict[str, Any] = {
            "channel": channel,
            "limit": tool_parameters.get("limit") or 100,
            "cursor": tool_parameters.get("cursor"),
        }

        try:
            response = client.call("conversations.members", "GET", params=params)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Request failed: {e}")
            return

        ok, data, error = slack_result(response)
        yield self.create_json_message(data)
        if not ok:
            yield self.create_text_message(f"Slack error: {error}")
            return
        members = data.get("members", [])
        yield self.create_text_message(f"Retrieved {len(members)} member(s).")
