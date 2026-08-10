from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListTeamsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            yield self.create_text_message("Access token is required in credentials.")
            return

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        url = "https://graph.microsoft.com/v1.0/me/joinedTeams"

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
        teams = [
            {
                "id": team.get("id"),
                "displayName": team.get("displayName"),
                "description": team.get("description"),
            }
            for team in data.get("value", [])
        ]

        if not teams:
            yield self.create_text_message("No joined teams found.")
        else:
            summary = "\n".join(
                f"{team['displayName']} ({team['id']})" for team in teams
            )
            yield self.create_text_message(f"Found {len(teams)} team(s):\n{summary}")

        yield self.create_json_message({"teams": teams})
