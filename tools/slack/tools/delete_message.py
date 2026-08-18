from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_api import SlackApiError, SlackClient


class DeleteMessageTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("Slack Access Token is required.")
            return

        channel = (tool_parameters.get("channel") or "").strip()
        ts = (tool_parameters.get("ts") or "").strip()

        if not channel or not ts:
            yield self.create_text_message("Both 'channel' and 'ts' are required.")
            return

        try:
            client = SlackClient(token)
            resp = client.api_call("chat.delete", {"channel": channel, "ts": ts})
        except SlackApiError as e:
            yield self.create_text_message(f"Failed to delete message: {e.slack_error}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        yield self.create_text_message(
            f"Message {resp.get('ts')} deleted from {resp.get('channel')}."
        )
        yield self.create_json_message(resp)
