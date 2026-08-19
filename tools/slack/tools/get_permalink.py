from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from slack_api import SlackApiError, SlackClient


class GetPermalinkTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("Slack Access Token is required.")
            return

        channel = (tool_parameters.get("channel") or "").strip()
        message_ts = (tool_parameters.get("message_ts") or "").strip()

        if not channel or not message_ts:
            yield self.create_text_message("Both 'channel' and 'message_ts' are required.")
            return

        try:
            client = SlackClient(token)
            resp = client.api_call(
                "chat.getPermalink", {"channel": channel, "message_ts": message_ts}
            )
        except SlackApiError as e:
            yield self.create_text_message(f"Failed to get permalink: {e.slack_error}")
            return
        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        yield self.create_text_message(resp.get("permalink", ""))
        yield self.create_json_message(resp)
