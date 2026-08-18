from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_api import SlackApiError, SlackClient


class RemoveReactionTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("Slack Access Token is required.")
            return

        channel = (tool_parameters.get("channel") or "").strip()
        timestamp = (tool_parameters.get("timestamp") or "").strip()
        name = (tool_parameters.get("name") or "").strip().strip(":")

        if not channel or not timestamp or not name:
            yield self.create_text_message(
                "The 'channel', 'timestamp' and 'name' parameters are all required."
            )
            return

        try:
            client = SlackClient(token)
            resp = client.api_call(
                "reactions.remove",
                {"channel": channel, "timestamp": timestamp, "name": name},
            )
        except SlackApiError as e:
            yield self.create_text_message(f"Failed to remove reaction: {e.slack_error}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        yield self.create_text_message(f"Removed :{name}: from message {timestamp}.")
        yield self.create_json_message(resp)
