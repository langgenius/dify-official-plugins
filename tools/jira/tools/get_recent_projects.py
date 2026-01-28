from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import auth


class GetRecentProjectsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        jira = auth(self.runtime.credentials)

        expand = tool_parameters.get("expand", "")
        properties = tool_parameters.get("properties", "")

        try:
            # Build query parameters for the request
            # Note: atlassian-python-api doesn't have a built-in recent_projects() method,
            # so we use the generic get() method with the endpoint path
            params = {}
            if expand:
                params["expand"] = expand
            if properties:
                params["properties"] = properties

            recent_projects = jira.get("project/recent", params=params)

            if not recent_projects:
                yield self.create_json_message(
                    {
                        "projects": [],
                        "message": "No recent projects found.",
                    }
                )
                return

            yield self.create_json_message(
                {
                    "projects": recent_projects,
                    "total": len(recent_projects) if isinstance(recent_projects, list) else 0,
                }
            )

        except Exception as e:
            error_details = str(e)
            if hasattr(e, 'response') and hasattr(e.response, 'text') and e.response.text:
                error_details = e.response.text
            yield self.create_json_message(
                {
                    "error": f"Error occurred while fetching recent projects: {error_details}",
                }
            )
