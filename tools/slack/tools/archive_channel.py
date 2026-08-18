from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_api import SlackApiError, SlackClient


class ArchiveChannelTool(Tool):
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
            resp = client.api_call("conversations.archive", {"channel": channel})
        except SlackApiError as e:
            yield self.create_text_message(f"Failed to archive channel: {e.slack_error}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        yield self.create_text_message(f"Channel {channel} archived.")
        yield self.create_json_message(resp)
