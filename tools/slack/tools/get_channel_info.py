from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_api import SlackApiError, SlackClient


class GetChannelInfoTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("Slack Access Token is required.")
            return

        channel = (tool_parameters.get("channel") or "").strip()
        if not channel:
            yield self.create_text_message("The 'channel' parameter is required.")
            return

        try:
            client = SlackClient(token)
            resp = client.api_call("conversations.info", {"channel": channel})
        except SlackApiError as e:
            yield self.create_text_message(f"Failed to get channel info: {e.slack_error}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        ch = resp.get("channel", {})
        yield self.create_text_message(
            f"Channel {ch.get('name')} (id: {ch.get('id')}), members: {ch.get('num_members', 'n/a')}."
        )
        yield self.create_json_message(resp)
