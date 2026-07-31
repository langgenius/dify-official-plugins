from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_client import SlackClient, SlackConfigError
from tool_utils import slack_result


class OpenChannelTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = SlackClient(self.runtime.credentials)
        except SlackConfigError as e:
            yield self.create_text_message(str(e))
            return

        users = (tool_parameters.get("users") or "").strip()
        channel = (tool_parameters.get("channel") or "").strip()
        if not users and not channel:
            yield self.create_text_message("Provide either 'users' or 'channel'.")
            return

        body: dict[str, Any] = {}
        if channel:
            body["channel"] = channel
        if users:
            body["users"] = ",".join(u.strip() for u in users.split(",") if u.strip())
        if tool_parameters.get("return_im"):
            body["return_im"] = True

        try:
            response = client.call("conversations.open", "POST", json_body=body)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Request failed: {e}")
            return

        ok, data, error = slack_result(response)
        yield self.create_json_message(data)
        if not ok:
            yield self.create_text_message(f"Slack error: {error}")
            return
        opened = data.get("channel", {})
        yield self.create_text_message(
            f"Conversation opened (ID {opened.get('id')})."
        )
