from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphError, resolve_graph_context
from tools.outputs import with_outputs


class ListTeamsTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            graph = resolve_graph_context(self.runtime.credentials)
        except GraphError as e:
            yield self.create_text_message(str(e))
            return
        access_token = graph.access_token

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        url = f"{graph.api_base}/me/joinedTeams"

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

        self._out.update(teams=[{"id": t.get("id") or "", "name": t.get("displayName") or "", "description": t.get("description") or "", "web_url": t.get("webUrl") or ""} for t in data.get("value", [])], count=len(teams), success=True)
        yield self.create_json_message({"teams": teams})
