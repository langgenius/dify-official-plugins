from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_api import SlackApiError, SlackClient


class CreateChannelTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("Slack Access Token is required.")
            return

        name = (tool_parameters.get("name") or "").strip()
        is_private = bool(tool_parameters.get("is_private", False))

        if not name:
            yield self.create_text_message("The 'name' parameter is required.")
            return

        try:
            client = SlackClient(token)
            resp = client.api_call(
                "conversations.create", {"name": name, "is_private": is_private}
            )
        except SlackApiError as e:
            yield self.create_text_message(f"Failed to create channel: {e.slack_error}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        ch = resp.get("channel", {})
        yield self.create_text_message(
            f"Channel {ch.get('name')} created (id: {ch.get('id')})."
        )
        yield self.create_json_message(resp)
