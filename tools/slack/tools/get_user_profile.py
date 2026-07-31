from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_client import SlackClient, SlackConfigError
from tool_utils import slack_result


class GetUserProfileTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = SlackClient(self.runtime.credentials)
        except SlackConfigError as e:
            yield self.create_text_message(str(e))
            return

        user = (tool_parameters.get("user") or "").strip()
        if not user:
            yield self.create_text_message("User ID is required.")
            return

        params: dict[str, Any] = {"user": user}
        if tool_parameters.get("include_labels"):
            params["include_labels"] = "true"

        try:
            response = client.call("users.profile.get", "GET", params=params)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Request failed: {e}")
            return

        ok, data, error = slack_result(response)
        yield self.create_json_message(data)
        if not ok:
            yield self.create_text_message(f"Slack error: {error}")
            return
        yield self.create_text_message(f"Profile for {user} retrieved.")
