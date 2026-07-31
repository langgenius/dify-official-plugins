from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_client import SlackClient, SlackConfigError
from tool_utils import slack_result


class ListFilesTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = SlackClient(self.runtime.credentials)
        except SlackConfigError as e:
            yield self.create_text_message(str(e))
            return

        params: dict[str, Any] = {
            "channel": tool_parameters.get("channel"),
            "user": tool_parameters.get("user"),
            "types": tool_parameters.get("types"),
            "count": tool_parameters.get("count") or 100,
            "page": tool_parameters.get("page") or 1,
        }

        try:
            response = client.call("files.list", "GET", params=params)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Request failed: {e}")
            return

        ok, data, error = slack_result(response)
        yield self.create_json_message(data)
        if not ok:
            yield self.create_text_message(f"Slack error: {error}")
            return
        files = data.get("files", [])
        yield self.create_text_message(f"Retrieved {len(files)} file(s).")
