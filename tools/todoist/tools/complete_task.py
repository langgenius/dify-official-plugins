from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import get_client


class CompleteTaskTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Mark a task as completed in Todoist
        """
        # Get parameters
        task_id = tool_parameters.get("task_id")

        # Validate parameters
        if not task_id:
            yield self.create_text_message("Task ID is required.")
            return

        try:
            api = get_client(self.runtime.credentials)

            # Complete task
            success = api.complete_task(task_id=task_id)

            # Create response
            if success:
                yield self.create_text_message(f"Successfully completed task {task_id}")
                yield self.create_json_message({"success": True, "task_id": task_id})
            else:
                yield self.create_text_message(f"Failed to complete task {task_id}")
                yield self.create_json_message({"success": False, "task_id": task_id})

        except Exception as e:
            yield self.create_text_message(f"Error completing task: {str(e)}")
            return
