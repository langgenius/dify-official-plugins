from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_api import SlackApiError, SlackClient


class UpdateMessageTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("Slack Access Token is required.")
            return

        channel = (tool_parameters.get("channel") or "").strip()
        ts = (tool_parameters.get("ts") or "").strip()
        text = tool_parameters.get("text") or ""

        if not channel or not ts:
            yield self.create_text_message("Both 'channel' and 'ts' are required.")
            return
        if not text:
            yield self.create_text_message("The 'text' parameter is required.")
            return

        try:
            client = SlackClient(token)
            resp = client.api_call(
                "chat.update", {"channel": channel, "ts": ts, "text": text}
            )
        except SlackApiError as e:
            yield self.create_text_message(f"Failed to update message: {e.slack_error}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        yield self.create_text_message(
            f"Message {resp.get('ts')} in {resp.get('channel')} updated."
        )
        yield self.create_json_message(resp)
