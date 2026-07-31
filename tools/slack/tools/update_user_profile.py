from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_client import SlackClient, SlackConfigError
from tool_utils import parse_json_param, slack_result


class UpdateUserProfileTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = SlackClient(self.runtime.credentials, require_user_token=True)
        except SlackConfigError as e:
            yield self.create_text_message(str(e))
            return

        body: dict[str, Any] = {}
        profile_raw = tool_parameters.get("profile")
        if profile_raw:
            try:
                profile = parse_json_param(profile_raw)
            except ValueError as e:
                yield self.create_text_message(f"Invalid Profile JSON: {e}")
                return
            if not isinstance(profile, dict):
                yield self.create_text_message("Profile must be a JSON object.")
                return
            body["profile"] = profile
        else:
            name = (tool_parameters.get("name") or "").strip()
            if not name:
                yield self.create_text_message(
                    "Provide a 'profile' JSON object or a 'name' + 'value'."
                )
                return
            body["name"] = name
            body["value"] = tool_parameters.get("value") or ""

        if tool_parameters.get("user"):
            body["user"] = tool_parameters.get("user")

        try:
            response = client.call("users.profile.set", "POST", json_body=body)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Request failed: {e}")
            return

        ok, data, error = slack_result(response)
        yield self.create_json_message(data)
        if not ok:
            yield self.create_text_message(f"Slack error: {error}")
            return
        yield self.create_text_message("Profile updated.")
