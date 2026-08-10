from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_api import SlackApiError, SlackClient


class ScheduleMessageTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("Slack Access Token is required.")
            return

        channel = (tool_parameters.get("channel") or "").strip()
        text = tool_parameters.get("text") or ""
        post_at = tool_parameters.get("post_at")

        if not channel:
            yield self.create_text_message("The 'channel' parameter is required.")
            return
        if not text:
            yield self.create_text_message("The 'text' parameter is required.")
            return
        if post_at in (None, ""):
            yield self.create_text_message("The 'post_at' parameter is required.")
            return

        try:
            post_at_int = int(post_at)
        except (TypeError, ValueError):
            yield self.create_text_message("'post_at' must be a Unix epoch timestamp in seconds.")
            return

        try:
            client = SlackClient(token)
            resp = client.api_call(
                "chat.scheduleMessage",
                {"channel": channel, "text": text, "post_at": post_at_int},
            )
        except SlackApiError as e:
            yield self.create_text_message(f"Failed to schedule message: {e.slack_error}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        yield self.create_text_message(
            f"Message scheduled in {resp.get('channel')} "
            f"(scheduled_message_id: {resp.get('scheduled_message_id')}, post_at: {resp.get('post_at')})."
        )
        yield self.create_json_message(resp)
