from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_client import SlackClient, SlackConfigError
from tool_utils import slack_result


class ListUsergroupsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = SlackClient(self.runtime.credentials)
        except SlackConfigError as e:
            yield self.create_text_message(str(e))
            return

        params: dict[str, Any] = {}
        if tool_parameters.get("include_disabled"):
            params["include_disabled"] = "true"
        if tool_parameters.get("include_count"):
            params["include_count"] = "true"
        if tool_parameters.get("include_users"):
            params["include_users"] = "true"

        try:
            response = client.call("usergroups.list", "GET", params=params)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Request failed: {e}")
            return

        ok, data, error = slack_result(response)
        yield self.create_json_message(data)
        if not ok:
            yield self.create_text_message(f"Slack error: {error}")
            return
        groups = data.get("usergroups", [])
        yield self.create_text_message(f"Retrieved {len(groups)} user group(s).")
