from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListTaskListsTool(Tool):
    """
    Tool to list all task lists in Google Tasks.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        List all task lists for the authenticated user.
        """
        # Get credentials
        if "access_token" not in self.runtime.credentials:
            yield self.create_text_message(
                "Access token is required. Please authorize with Google first."
            )
            return

        access_token = self.runtime.credentials.get("access_token")

        # Optional parameters
        max_results = tool_parameters.get("max_results", 100)

        # Make API request
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        params = {"maxResults": max_results}

        try:
            response = requests.get(
                "https://tasks.googleapis.com/tasks/v1/users/@me/lists",
                headers=headers,
                params=params,
                timeout=30,
            )

            if response.status_code == 401:
                yield self.create_text_message(
                    "Authentication failed. Please re-authorize with Google."
                )
                return
            elif response.status_code != 200:
                yield self.create_text_message(
                    f"Failed to list task lists: {response.text}"
                )
                return

            data = response.json()
            task_lists = data.get("items", [])

            # Return structured data
            yield self.create_json_message(
                {"task_lists": task_lists, "count": len(task_lists)}
            )

            # Create readable summary
            if task_lists:
                summary = f"Found {len(task_lists)} task list(s):\n\n"
                for task_list in task_lists:
                    title = task_list.get("title", "Untitled")
                    list_id = task_list.get("id")
                    updated = task_list.get("updated", "")
                    summary += f"• {title}\n  ID: {list_id}\n  Updated: {updated}\n\n"
                yield self.create_text_message(summary)
            else:
                yield self.create_text_message("No task lists found.")

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")
