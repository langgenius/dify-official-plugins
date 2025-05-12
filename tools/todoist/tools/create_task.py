from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import get_client


class CreateTaskTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a new task in Todoist
        """
        # Get parameters
        content = tool_parameters.get("content")
        project_id = tool_parameters.get("project_id", None)
        due_string = tool_parameters.get("due_string", "tomorrow")
        priority = tool_parameters.get("priority", 1)

        # Validate parameters
        if not content:
            yield self.create_text_message("Task content is required.")
            return

        if not project_id:
            yield self.create_text_message("Project ID is required.")
            return

        try:
            api = get_client(self.runtime.credentials)

            # Create task
            task = api.add_task(
                content=content,
                project_id=project_id,
                due_string=due_string,
                priority=priority,
            )

            # Create response
            summary = f"Successfully created task: {task.content}"
            if project_id:
                summary += f" in project {project_id}"
            if due_string:
                summary += f" due {due_string}"
            if priority > 1:
                priority_text = (
                    "high" if priority == 4 else "medium" if priority == 3 else "low"
                )
                summary += f" with {priority_text} priority"

            yield self.create_text_message(summary)

            yield self.create_json_message({"task": task.to_dict()})

        except Exception as e:
            yield self.create_text_message(f"Error creating task: {str(e)}")
            return
