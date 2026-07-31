from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_client import SlackClient, SlackConfigError
from tool_utils import slack_result


class CreateChannelTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = SlackClient(self.runtime.credentials)
        except SlackConfigError as e:
            yield self.create_text_message(str(e))
            return

        name = (tool_parameters.get("name") or "").strip()
        if not name:
            yield self.create_text_message("Channel name is required.")
            return

        body = {"name": name, "is_private": bool(tool_parameters.get("is_private"))}
        try:
            response = client.call("conversations.create", "POST", json_body=body)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Request failed: {e}")
            return

        ok, data, error = slack_result(response)
        yield self.create_json_message(data)
        if not ok:
            yield self.create_text_message(f"Slack error: {error}")
            return
        channel = data.get("channel", {})
        yield self.create_text_message(
            f"Channel '{channel.get('name', name)}' created (ID {channel.get('id')})."
        )
