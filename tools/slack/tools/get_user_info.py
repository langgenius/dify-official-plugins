from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_api import SlackApiError, SlackClient


class GetUserInfoTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("Slack Access Token is required.")
            return

        user = (tool_parameters.get("user") or "").strip()
        if not user:
            yield self.create_text_message("The 'user' parameter is required.")
            return

        try:
            client = SlackClient(token)
            resp = client.api_call("users.info", {"user": user})
        except SlackApiError as e:
            yield self.create_text_message(f"Failed to get user info: {e.slack_error}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        u = resp.get("user", {})
        yield self.create_text_message(
            f"User {u.get('name')} (id: {u.get('id')}, real_name: {u.get('real_name', '')})."
        )
        yield self.create_json_message(resp)
