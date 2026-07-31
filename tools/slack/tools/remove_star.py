from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_client import SlackClient, SlackConfigError
from tool_utils import slack_result


class RemoveStarTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = SlackClient(self.runtime.credentials, require_user_token=True)
        except SlackConfigError as e:
            yield self.create_text_message(str(e))
            return

        channel = (tool_parameters.get("channel") or "").strip()
        timestamp = (tool_parameters.get("timestamp") or "").strip()
        file_id = (tool_parameters.get("file") or "").strip()

        body: dict[str, Any] = {}
        if file_id:
            body["file"] = file_id
        elif channel and timestamp:
            body["channel"] = channel
            body["timestamp"] = timestamp
        else:
            yield self.create_text_message(
                "Provide either 'file' or both 'channel' and 'timestamp'."
            )
            return

        try:
            response = client.call("stars.remove", "POST", json_body=body)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Request failed: {e}")
            return

        ok, data, error = slack_result(response)
        yield self.create_json_message(data)
        if not ok:
            yield self.create_text_message(f"Slack error: {error}")
            return
        yield self.create_text_message("Star removed.")
