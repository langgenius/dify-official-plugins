from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from todoist_api_python.models import Project

from tools.auth import get_client


class ListProjectsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        List all projects from Todoist
        """
        try:
            api = get_client(self.runtime.credentials)

            # Get projects
            project_lists = api.get_projects()

            # Convert projects to list and create summary
            projects: list[Project] = []
            for project_list in project_lists:
                projects.extend(project_list)

            summary = f"Found {len(projects)} projects"

            # Create response
            yield self.create_text_message(summary)

            yield self.create_json_message(
                {"projects": [project.to_dict() for project in projects]}
            )

        except Exception as e:
            yield self.create_text_message(f"Error listing projects: {str(e)}")
            return
