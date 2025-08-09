from collections.abc import Generator
from datetime import datetime
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class CreateTaskTool(Tool):
    """
    Tool to create a new task in Google Tasks.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a new task in a specific task list.
        """
        # Get credentials
        if "access_token" not in self.runtime.credentials:
            yield self.create_text_message(
                "Access token is required. Please authorize with Google first."
            )
            return

        access_token = self.runtime.credentials.get("access_token")

        # Required parameters
        title = tool_parameters.get("title")
        if not title:
            yield self.create_text_message("Task title is required.")
            return

        # Optional parameters
        tasklist_id = tool_parameters.get("tasklist_id", "@default")
        notes = tool_parameters.get("notes", "")
        due_date = tool_parameters.get("due_date")
        parent_task_id = tool_parameters.get("parent_task_id")
        previous_task_id = tool_parameters.get("previous_task_id")

        # Build task data
        task_data = {"title": title}

        if notes:
            task_data["notes"] = notes

        if due_date:
            # Convert to RFC 3339 format if needed
            try:
                # If it's already in RFC 3339 format, use it directly
                if "T" in due_date:
                    task_data["due"] = due_date
                else:
                    # Convert date string to RFC 3339
                    dt = datetime.strptime(due_date, "%Y-%m-%d")
                    task_data["due"] = dt.strftime("%Y-%m-%dT00:00:00.000Z")
            except ValueError:
                yield self.create_text_message(
                    f"Invalid date format: {due_date}. Use YYYY-MM-DD or RFC 3339 format."
                )
                return

        # Make API request
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        params = {}
        if parent_task_id:
            params["parent"] = parent_task_id
        if previous_task_id:
            params["previous"] = previous_task_id

        try:
            response = requests.post(
                f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist_id}/tasks",
                headers=headers,
                params=params,
                json=task_data,
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
                yield self.create_text_message(
                    f"Failed to create task: {response.text}"
                )
                return

            created_task = response.json()

            # Return structured data
            yield self.create_json_message(
                {
                    "task": created_task,
                    "success": True,
                    "message": "Task created successfully",
                }
            )

            # Create readable summary
            task_id = created_task.get("id")
            title = created_task.get("title")
            status = created_task.get("status", "needsAction")
            due = created_task.get("due", "")

            summary = f"✅ Task created successfully!\n\n"
            summary += f"Title: {title}\n"
            summary += f"ID: {task_id}\n"
            summary += f"Status: {status}\n"
            if due:
                summary += f"Due: {due}\n"
            if notes:
                summary += f"Notes: {notes}\n"

            yield self.create_text_message(summary)

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")
