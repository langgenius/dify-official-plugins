from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_client import SlackClient, SlackConfigError
from tool_utils import slack_result


class ListChannelsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = SlackClient(self.runtime.credentials)
        except SlackConfigError as e:
            yield self.create_text_message(str(e))
            return

        params: dict[str, Any] = {
            "types": tool_parameters.get("types") or "public_channel",
            "limit": tool_parameters.get("limit") or 100,
            "cursor": tool_parameters.get("cursor"),
            "exclude_archived": "true"
            if tool_parameters.get("exclude_archived", True)
            else "false",
        }

        try:
            response = client.call("conversations.list", "GET", params=params)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Request failed: {e}")
            return

        ok, data, error = slack_result(response)
        yield self.create_json_message(data)
        if not ok:
            yield self.create_text_message(f"Slack error: {error}")
            return
        channels = data.get("channels", [])
        cursor = data.get("response_metadata", {}).get("next_cursor")
        yield self.create_text_message(
            f"Retrieved {len(channels)} channel(s)."
            + (" More pages available." if cursor else "")
        )
