from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphAuthError, describe_error, resolve_graph_context


class ListCalendarGroupsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        List the calendar groups of the mailbox (e.g. "My Calendars", "People's calendars").
        Calendars other people shared with the user usually sit in "People's calendars".
        """
        try:
            try:
                graph = resolve_graph_context(self.runtime.credentials, tool_parameters.get("mailbox"))
            except GraphAuthError as e:
                yield self.create_text_message(str(e))
                return

            try:
                response = requests.get(
                    f"{graph.mailbox_base}/calendarGroups",
                    headers={"Authorization": f"Bearer {graph.access_token}"},
                    params={"$select": "id,name,classId", "$top": 100},
                    timeout=30,
                )
            except requests.exceptions.RequestException as e:
                yield self.create_text_message(f"Network error: {str(e)}")
                return
            if response.status_code < 200 or response.status_code >= 300:
                yield self.create_text_message(describe_error(response))
                return

            groups = [{"id": g.get("id"), "name": g.get("name")} for g in response.json().get("value", [])]
            summary = "\n".join(f"- {g['name']} (id: {g['id']})" for g in groups)
            yield self.create_text_message(
                f"Found {len(groups)} calendar group(s):\n{summary}" if groups else "No calendar groups found."
            )
            yield self.create_json_message({"calendar_groups": groups})

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
