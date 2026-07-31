from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_client import SlackClient, SlackConfigError
from tool_utils import slack_result


class CreateUsergroupTool(Tool):
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
            yield self.create_text_message("Name is required.")
            return

        body: dict[str, Any] = {"name": name}
        if tool_parameters.get("handle"):
            body["handle"] = tool_parameters.get("handle")
        if tool_parameters.get("description"):
            body["description"] = tool_parameters.get("description")
        channels = (tool_parameters.get("channels") or "").strip()
        if channels:
            body["channels"] = ",".join(
                c.strip() for c in channels.split(",") if c.strip()
            )

        try:
            response = client.call("usergroups.create", "POST", json_body=body)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Request failed: {e}")
            return

        ok, data, error = slack_result(response)
        yield self.create_json_message(data)
        if not ok:
            yield self.create_text_message(f"Slack error: {error}")
            return
        group = data.get("usergroup", {})
        yield self.create_text_message(
            f"User group '{group.get('name', name)}' created (ID {group.get('id')})."
        )
