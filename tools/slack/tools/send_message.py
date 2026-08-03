from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_api import SlackApiError, SlackClient


class SendMessageTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("Slack Access Token is required.")
            return

        channel = (tool_parameters.get("channel") or "").strip()
        text = tool_parameters.get("text") or ""
        thread_ts = (tool_parameters.get("thread_ts") or "").strip() or None

        if not channel:
            yield self.create_text_message("The 'channel' parameter is required.")
            return
        if not text:
            yield self.create_text_message("The 'text' parameter is required.")
            return

        try:
            client = SlackClient(token)
            resp = client.api_call(
                "chat.postMessage",
                {"channel": channel, "text": text, "thread_ts": thread_ts},
            )
        except SlackApiError as e:
            yield self.create_text_message(f"Failed to send message: {e.slack_error}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        yield self.create_text_message(
            f"Message sent to {resp.get('channel')} (ts: {resp.get('ts')})."
        )
        yield self.create_json_message(resp)
