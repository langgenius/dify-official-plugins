from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListChatsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            yield self.create_text_message("Access token is required in credentials.")
            return

        try:
            top = int(tool_parameters.get("top") or 20)
        except (TypeError, ValueError):
            top = 20

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        url = "https://graph.microsoft.com/v1.0/me/chats"
        params = {"$top": top}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
            return

        if response.status_code < 200 or response.status_code >= 300:
            yield self.create_text_message(
                f"API error {response.status_code}: {response.text}"
            )
            return

        data = response.json()
        chats = [
            {
                "id": chat.get("id"),
                "topic": chat.get("topic"),
                "chatType": chat.get("chatType"),
            }
            for chat in data.get("value", [])
        ]

        if not chats:
            yield self.create_text_message("No chats found.")
        else:
            summary = "\n".join(
                f"{chat['topic'] or chat['chatType']} ({chat['id']})" for chat in chats
            )
            yield self.create_text_message(f"Found {len(chats)} chat(s):\n{summary}")

        yield self.create_json_message({"chats": chats})
