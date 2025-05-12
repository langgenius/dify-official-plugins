from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from todoist_api_python.models import Task

from tools.auth import get_client


class ListTasksTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        List tasks from Todoist project
        """
        # Get parameters
        project_id = tool_parameters.get("project_id", None)
        if not project_id:
            yield self.create_text_message("Project ID is required.")
            return

        try:
            api = get_client(self.runtime.credentials)

            # Get tasks
            task_lists = api.get_tasks(project_id=project_id)

            # Convert tasks to list and create summary
            tasks: list[Task] = []
            for task in task_lists:
                tasks.extend(task)

            summary = f"Found {len(tasks)} tasks"

            # Create response
            yield self.create_text_message(summary)

            yield self.create_json_message(
                {"tasks": [task.to_dict() for task in tasks]}
            )

        except Exception as e:
            yield self.create_text_message(f"Error listing tasks: {str(e)}")
            return
