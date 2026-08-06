from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class SendChatMessageTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            yield self.create_text_message("Access token is required in credentials.")
            return

        chat_id = tool_parameters.get("chat_id", "")
        message = tool_parameters.get("message", "")
        content_type = tool_parameters.get("content_type") or "html"

        if not chat_id:
            yield self.create_text_message("chat_id is required.")
            return
        if not message:
            yield self.create_text_message("message is required.")
            return
        if content_type not in ("html", "text"):
            content_type = "html"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        url = f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages"
        body = {"body": {"contentType": content_type, "content": message}}

        try:
            response = requests.post(url, headers=headers, json=body, timeout=30)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
            return

        if response.status_code < 200 or response.status_code >= 300:
            yield self.create_text_message(
                f"API error {response.status_code}: {response.text}"
            )
            return

        data = response.json()
        yield self.create_text_message(
            f"Message sent to chat. Message ID: {data.get('id')}"
        )
        yield self.create_json_message(data)
