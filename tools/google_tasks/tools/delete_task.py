from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class DeleteTaskTool(Tool):
    """
    Tool to delete a task from Google Tasks.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Delete a task from Google Tasks.
        """
        # Get credentials
        if "access_token" not in self.runtime.credentials:
            yield self.create_text_message(
                "Access token is required. Please authorize with Google first."
            )
            return

        access_token = self.runtime.credentials.get("access_token")

        # Required parameters
        task_id = tool_parameters.get("task_id")
        if not task_id:
            yield self.create_text_message("Task ID is required.")
            return

        # Optional parameters
        tasklist_id = tool_parameters.get("tasklist_id", "@default")

        # Make API request
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        try:
            # First, get the task details for confirmation
            response = requests.get(
                f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist_id}/tasks/{task_id}",
                headers=headers,
                timeout=30,
            )

            if response.status_code == 404:
                yield self.create_text_message(
                    f"Task '{task_id}' not found in list '{tasklist_id}'."
                )
                return
            elif response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Please re-authorize with Google."
                )
                return
            elif response.status_code != 200:
                yield self.create_text_message(f"Failed to get task: {response.text}")
                return

            task_to_delete = response.json()
            task_title = task_to_delete.get("title", "Untitled")

            # Now delete the task
            response = requests.delete(
                f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist_id}/tasks/{task_id}",
                headers=headers,
                timeout=30,
            )

            if response.status_code == 204:
                # Successful deletion (no content)
                yield self.create_json_message(
                    {
                        "success": True,
                        "message": f"Task '{task_title}' deleted successfully",
                        "deleted_task_id": task_id,
                        "deleted_task_title": task_title,
                    }
                )

                summary = f"✅ Task deleted successfully!\n\n"
                summary += f"Deleted Task: {task_title}\n"
                summary += f"Task ID: {task_id}\n"
                summary += f"From List: {tasklist_id}"

                yield self.create_text_message(summary)
            else:
                yield self.create_text_message(
                    f"Failed to delete task: Status {response.status_code} - {response.text}"
                )

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")
