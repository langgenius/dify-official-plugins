from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListTasksTool(Tool):
    """
    Tool to list tasks in a specific task list.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        List tasks from a specific task list.
        """
        # Get credentials
        if "access_token" not in self.runtime.credentials:
            yield self.create_text_message(
                "Access token is required. Please authorize with Google first."
            )
            return

        access_token = self.runtime.credentials.get("access_token")

        # Required parameters
        tasklist_id = tool_parameters.get("tasklist_id", "@default")

        # Optional parameters
        max_results = tool_parameters.get("max_results", 100)
        show_completed = tool_parameters.get("show_completed", True)
        show_deleted = tool_parameters.get("show_deleted", False)
        show_hidden = tool_parameters.get("show_hidden", False)
        due_min = tool_parameters.get("due_min")
        due_max = tool_parameters.get("due_max")
        completed_min = tool_parameters.get("completed_min")
        completed_max = tool_parameters.get("completed_max")

        # Make API request
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        params = {
            "maxResults": max_results,
            "showCompleted": show_completed,
            "showDeleted": show_deleted,
            "showHidden": show_hidden,
        }

        # Add optional date filters
        if due_min:
            params["dueMin"] = due_min
        if due_max:
            params["dueMax"] = due_max
        if completed_min:
            params["completedMin"] = completed_min
        if completed_max:
            params["completedMax"] = completed_max

        try:
            response = requests.get(
                f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist_id}/tasks",
                headers=headers,
                params=params,
                timeout=30,
            )

            if response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Please re-authorize with Google."
                )
                return
            elif response.status_code == 404:
                yield self.create_text_message(f"Task list '{tasklist_id}' not found.")
                return
            elif response.status_code != 200:
                yield self.create_text_message(f"Failed to list tasks: {response.text}")
                return

            data = response.json()
            tasks = data.get("items", [])

            # Return structured data
            yield self.create_json_message(
                {"tasks": tasks, "count": len(tasks), "tasklist_id": tasklist_id}
            )

            # Create readable summary
            if tasks:
                summary = f"Found {len(tasks)} task(s) in list '{tasklist_id}':\n\n"
                for task in tasks:
                    title = task.get("title", "Untitled")
                    task_id = task.get("id")
                    status = task.get("status", "needsAction")
                    due = task.get("due", "")
                    notes = task.get("notes", "")

                    status_icon = "✓" if status == "completed" else "○"
                    summary += f"{status_icon} {title}\n"
                    summary += f"  ID: {task_id}\n"
                    if due:
                        summary += f"  Due: {due}\n"
                    if notes:
                        summary += (
                            f"  Notes: {notes[:50]}{'...' if len(notes) > 50 else ''}\n"
                        )
                    summary += "\n"
                yield self.create_text_message(summary)
            else:
                yield self.create_text_message(
                    f"No tasks found in list '{tasklist_id}'."
                )

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")
