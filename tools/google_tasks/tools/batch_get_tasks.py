from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class BatchGetTasksTool(Tool):
    """
    Tool to batch get multiple tasks from Google Tasks.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Batch get multiple tasks by their IDs.
        """
        # Get credentials
        if "access_token" not in self.runtime.credentials:
            yield self.create_text_message(
                "Access token is required. Please authorize with Google first."
            )
            return

        access_token = self.runtime.credentials.get("access_token")

        # Required parameters
        task_ids = tool_parameters.get("task_ids")
        if not task_ids:
            yield self.create_text_message("Task IDs are required.")
            return

        # Parse task IDs if they're provided as a string
        if isinstance(task_ids, str):
            # Split by comma, semicolon, or newline
            task_ids = [
                tid.strip()
                for tid in task_ids.replace(";", ",").replace("\n", ",").split(",")
                if tid.strip()
            ]

        if not task_ids:
            yield self.create_text_message("No valid task IDs provided.")
            return

        # Optional parameters
        tasklist_id = tool_parameters.get("tasklist_id", "@default")

        # Make API requests
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        tasks = []
        errors = []

        try:
            for task_id in task_ids:
                try:
                    response = requests.get(
                        f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist_id}/tasks/{task_id}",
                        headers=headers,
                        timeout=30,
                    )

                    if response.status_code == 200:
                        task = response.json()
                        tasks.append(task)
                    elif response.status_code == 404:
                        errors.append({"task_id": task_id, "error": "Task not found"})
                    elif response.status_code == 401:
                        yield self.create_text_message(
                            "Authentication failed. Please re-authorize with Google."
                        )
                        return
                    else:
                        errors.append(
                            {
                                "task_id": task_id,
                                "error": f"Failed with status {response.status_code}",
                            }
                        )

                except requests.RequestException as e:
                    errors.append({"task_id": task_id, "error": str(e)})

            # Return structured data
            result = {
                "tasks": tasks,
                "count": len(tasks),
                "requested": len(task_ids),
                "success": len(errors) == 0,
            }

            if errors:
                result["errors"] = errors

            yield self.create_json_message(result)

            # Create readable summary
            summary = f"Batch Task Retrieval Results\n"
            summary += "=" * 40 + "\n\n"
            summary += f"Requested: {len(task_ids)} task(s)\n"
            summary += f"Retrieved: {len(tasks)} task(s)\n"

            if errors:
                summary += f"Failed: {len(errors)} task(s)\n"

            summary += "\n"

            if tasks:
                summary += "Successfully Retrieved Tasks:\n"
                summary += "-" * 30 + "\n"
                for task in tasks:
                    title = task.get("title", "Untitled")
                    task_id = task.get("id")
                    status = task.get("status", "needsAction")
                    due = task.get("due", "")

                    status_icon = "✓" if status == "completed" else "○"
                    summary += f"\n{status_icon} {title}\n"
                    summary += f"  ID: {task_id}\n"
                    summary += f"  Status: {status}\n"
                    if due:
                        summary += f"  Due: {due}\n"

            if errors:
                summary += "\n\nFailed to Retrieve:\n"
                summary += "-" * 30 + "\n"
                for error in errors:
                    summary += f"• Task ID: {error['task_id']}\n"
                    summary += f"  Error: {error['error']}\n"

            yield self.create_text_message(summary)

        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")
