from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import get_client


class GetTaskTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get details of a specific Todoist task
        """
        # Get parameters
        task_id = tool_parameters.get("task_id")

        # Validate parameters
        if not task_id:
            yield self.create_text_message("Task ID is required.")
            return

        try:
            api = get_client(self.runtime.credentials)

            # Get task
            task = api.get_task(task_id=task_id)

            # Create response
            summary = f"""Retrieved task:
ID: {task.id}
NAME: {task.content}
DESCRIPTION: {task.description}"""
            yield self.create_text_message(summary)

            yield self.create_json_message({"task": task.to_dict()})

        except Exception as e:
            yield self.create_text_message(f"Error getting task: {str(e)}")
            return
