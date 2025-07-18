from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import get_client


class GetProjectTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get details of a specific Todoist project
        """
        # Get parameters
        project_id = tool_parameters.get("project_id")

        # Validate parameters
        if not project_id:
            yield self.create_text_message("Project ID is required.")
            return

        try:
            api = get_client(self.runtime.credentials)

            # Get project
            project = api.get_project(project_id=project_id)

            # Create response
            summary = f"""Retrieved project:
ID: {project.id}
NAME: {project.name}
DESCRIPTION: {project.description}"""
            yield self.create_text_message(summary)

            yield self.create_json_message({"project": project.to_dict()})

        except Exception as e:
            yield self.create_text_message(f"Error getting project: {str(e)}")
            return
