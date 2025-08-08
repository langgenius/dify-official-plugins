from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class GetTaskTool(Tool):
    """
    Tool to get details of a specific task from Google Tasks.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get details of a specific task.
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
            response = requests.get(
                f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist_id}/tasks/{task_id}",
                headers=headers,
                timeout=30,
            )

            if response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Please re-authorize with Google."
                )
                return
            elif response.status_code == 404:
                yield self.create_text_message(
                    f"Task '{task_id}' not found in list '{tasklist_id}'."
                )
                return
            elif response.status_code != 200:
                yield self.create_text_message(f"Failed to get task: {response.text}")
                return

            task = response.json()

            # Return structured data
            yield self.create_json_message({"task": task, "success": True})

            # Create readable summary
            title = task.get("title", "Untitled")
            task_id = task.get("id")
            status = task.get("status", "needsAction")
            notes = task.get("notes", "")
            due = task.get("due", "")
            completed = task.get("completed", "")
            updated = task.get("updated", "")
            parent = task.get("parent", "")
            position = task.get("position", "")

            status_icon = "✓" if status == "completed" else "○"
            summary = f"{status_icon} Task Details\n"
            summary += "=" * 40 + "\n\n"
            summary += f"Title: {title}\n"
            summary += f"ID: {task_id}\n"
            summary += f"Status: {status}\n"
            summary += f"Last Updated: {updated}\n"

            if due:
                summary += f"Due Date: {due}\n"
            if completed:
                summary += f"Completed: {completed}\n"
            if parent:
                summary += f"Parent Task: {parent}\n"
            if position:
                summary += f"Position: {position}\n"
            if notes:
                summary += f"\nNotes:\n{notes}\n"

            # Check for subtasks
            if "links" in task:
                links = task["links"]
                for link in links:
                    if link.get("type") == "subtasks":
                        summary += (
                            f"\nSubtasks: {link.get('description', 'Has subtasks')}\n"
                        )

            yield self.create_text_message(summary)

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")
