from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_client import SlackClient, SlackConfigError
from tool_utils import slack_result


class UpdateUsergroupTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = SlackClient(self.runtime.credentials)
        except SlackConfigError as e:
            yield self.create_text_message(str(e))
            return

        usergroup = (tool_parameters.get("usergroup") or "").strip()
        if not usergroup:
            yield self.create_text_message("User Group ID is required.")
            return

        body: dict[str, Any] = {"usergroup": usergroup}
        for key in ("name", "handle", "description"):
            if tool_parameters.get(key):
                body[key] = tool_parameters.get(key)
        channels = (tool_parameters.get("channels") or "").strip()
        if channels:
            body["channels"] = ",".join(
                c.strip() for c in channels.split(",") if c.strip()
            )

        try:
            response = client.call("usergroups.update", "POST", json_body=body)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Request failed: {e}")
            return

        ok, data, error = slack_result(response)
        yield self.create_json_message(data)
        if not ok:
            yield self.create_text_message(f"Slack error: {error}")
            return
        yield self.create_text_message(f"User group {usergroup} updated.")
