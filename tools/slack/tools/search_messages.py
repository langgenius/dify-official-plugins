from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_client import SlackClient, SlackConfigError
from tool_utils import slack_result


class SearchMessagesTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = SlackClient(self.runtime.credentials, require_user_token=True)
        except SlackConfigError as e:
            yield self.create_text_message(str(e))
            return

        query = (tool_parameters.get("query") or "").strip()
        if not query:
            yield self.create_text_message("Query is required.")
            return

        params: dict[str, Any] = {
            "query": query,
            "count": tool_parameters.get("count") or 20,
            "page": tool_parameters.get("page") or 1,
            "sort": tool_parameters.get("sort") or "score",
        }

        try:
            response = client.call("search.messages", "GET", params=params)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Request failed: {e}")
            return

        ok, data, error = slack_result(response)
        yield self.create_json_message(data)
        if not ok:
            yield self.create_text_message(f"Slack error: {error}")
            return
        total = data.get("messages", {}).get("total", 0)
        yield self.create_text_message(f"Found {total} matching message(s).")
