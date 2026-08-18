from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_api import SlackApiError, SlackClient


class LookupUserByEmailTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("Slack Access Token is required.")
            return

        email = (tool_parameters.get("email") or "").strip()
        if not email:
            yield self.create_text_message("The 'email' parameter is required.")
            return

        try:
            client = SlackClient(token)
            resp = client.api_call("users.lookupByEmail", {"email": email})
        except SlackApiError as e:
            yield self.create_text_message(f"Failed to look up user: {e.slack_error}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        u = resp.get("user", {})
        yield self.create_text_message(
            f"Found user {u.get('name')} (id: {u.get('id')}) for {email}."
        )
        yield self.create_json_message(resp)
