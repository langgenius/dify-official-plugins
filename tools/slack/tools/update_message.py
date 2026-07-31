from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_client import SlackClient, SlackConfigError
from tool_utils import parse_json_param, slack_result


class UpdateMessageTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = SlackClient(self.runtime.credentials)
        except SlackConfigError as e:
            yield self.create_text_message(str(e))
            return

        channel = (tool_parameters.get("channel") or "").strip()
        ts = (tool_parameters.get("ts") or "").strip()
        if not channel or not ts:
            yield self.create_text_message("Channel and Message Timestamp are required.")
            return

        try:
            blocks = parse_json_param(tool_parameters.get("blocks"))
            attachments = parse_json_param(tool_parameters.get("attachments"))
        except ValueError as e:
            yield self.create_text_message(f"Invalid JSON parameter: {e}")
            return

        text = tool_parameters.get("text") or ""
        if not text and not blocks:
            yield self.create_text_message("Provide 'text' or 'blocks'.")
            return

        body: dict[str, Any] = {"channel": channel, "ts": ts}
        if text:
            body["text"] = text
        if blocks is not None:
            body["blocks"] = blocks
        if attachments is not None:
            body["attachments"] = attachments

        try:
            response = client.call("chat.update", "POST", json_body=body)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Request failed: {e}")
            return

        ok, data, error = slack_result(response)
        yield self.create_json_message(data)
        if not ok:
            yield self.create_text_message(f"Slack error: {error}")
            return
        yield self.create_text_message(f"Message {ts} updated in {channel}.")
