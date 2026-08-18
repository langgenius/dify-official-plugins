from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListChannelsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            yield self.create_text_message("Access token is required in credentials.")
            return

        team_id = tool_parameters.get("team_id", "")
        if not team_id:
            yield self.create_text_message("team_id is required.")
            return

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        url = f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels"

        try:
            response = requests.get(url, headers=headers, timeout=30)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
            return

        if response.status_code < 200 or response.status_code >= 300:
            yield self.create_text_message(
                f"API error {response.status_code}: {response.text}"
            )
            return

        data = response.json()
        channels = [
            {
                "id": channel.get("id"),
                "displayName": channel.get("displayName"),
                "description": channel.get("description"),
            }
            for channel in data.get("value", [])
        ]

        if not channels:
            yield self.create_text_message("No channels found for this team.")
        else:
            summary = "\n".join(
                f"{channel['displayName']} ({channel['id']})" for channel in channels
            )
            yield self.create_text_message(
                f"Found {len(channels)} channel(s):\n{summary}"
            )

        yield self.create_json_message({"channels": channels})
