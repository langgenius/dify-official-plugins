from collections.abc import Generator
from datetime import datetime
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class UpdateTaskTool(Tool):
    """
    Tool to update an existing task in Google Tasks.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Update an existing task in Google Tasks.
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
        title = tool_parameters.get("title")
        notes = tool_parameters.get("notes")
        due_date = tool_parameters.get("due_date")
        completed = tool_parameters.get("completed")
        deleted = tool_parameters.get("deleted")

        # First, get the current task to preserve existing data
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        try:
            # Get current task
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

            current_task = response.json()

            # Build update data based on current task
            update_data = current_task.copy()

            # Update fields if provided
            if title is not None:
                update_data["title"] = title

            if notes is not None:
                update_data["notes"] = notes

            if due_date is not None:
                if due_date == "":
                    # Remove due date
                    update_data.pop("due", None)
                else:
                    # Convert to RFC 3339 format if needed
                    try:
                        if "T" in due_date:
                            update_data["due"] = due_date
                        else:
                            dt = datetime.strptime(due_date, "%Y-%m-%d")
                            update_data["due"] = dt.strftime("%Y-%m-%dT00:00:00.000Z")
                    except ValueError:
                        yield self.create_text_message(
                            f"Invalid date format: {due_date}. Use YYYY-MM-DD or RFC 3339 format."
                        )
                        return

            if completed is not None:
                if completed:
                    update_data["status"] = "completed"
                    # Set completed time to now if not already set
                    if "completed" not in update_data:
                        update_data["completed"] = datetime.utcnow().strftime(
                            "%Y-%m-%dT%H:%M:%S.000Z"
                        )
                else:
                    update_data["status"] = "needsAction"
                    update_data.pop("completed", None)

            if deleted is not None:
                update_data["deleted"] = deleted

            # Make update request
            headers["Content-Type"] = "application/json"

            response = requests.put(
                f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist_id}/tasks/{task_id}",
                headers=headers,
                json=update_data,
                timeout=30,
            )

            if response.status_code != 200:
                yield self.create_text_message(
                    f"Failed to update task: {response.text}"
                )
                return

            updated_task = response.json()

            # Return structured data
            yield self.create_json_message(
                {
                    "task": updated_task,
                    "success": True,
                    "message": "Task updated successfully",
                }
            )

            # Create readable summary
            summary = f"✅ Task updated successfully!\n\n"
            summary += f"Title: {updated_task.get('title', 'Untitled')}\n"
            summary += f"ID: {updated_task.get('id')}\n"
            summary += f"Status: {updated_task.get('status', 'needsAction')}\n"

            if updated_task.get("due"):
                summary += f"Due: {updated_task['due']}\n"
            if updated_task.get("notes"):
                summary += f"Notes: {updated_task['notes'][:100]}{'...' if len(updated_task['notes']) > 100 else ''}\n"
            if updated_task.get("completed"):
                summary += f"Completed: {updated_task['completed']}\n"

            yield self.create_text_message(summary)

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")
