from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class GetUserInfoTool(Tool):
    """
    Tool for retrieving Hacker News user information.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get Hacker News user information by username.
        """
        # Extract parameters
        username = tool_parameters.get("username")
        if not username:
            yield self.create_text_message("Username is required")
            return

        try:
            # Log the operation start
            yield self.create_log_message(
                label="Fetching User Info",
                data={"username": username},
                status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
            )

            # Make API call to get user info
            api_url = f"https://hacker-news.firebaseio.com/v0/user/{username}.json"
            response = requests.get(api_url, timeout=10)

            if response.status_code == 404:
                yield self.create_text_message(
                    f"User '{username}' not found on Hacker News"
                )
                return

            if response.status_code != 200:
                yield self.create_text_message(
                    f"Failed to fetch user info. HTTP {response.status_code}"
                )
                return

            user_data = response.json()

            if not user_data:
                yield self.create_text_message(
                    f"User '{username}' not found on Hacker News"
                )
                return

            # Format user information
            user_info = {
                "username": user_data.get("id", "N/A"),
                "created": user_data.get("created", "N/A"),
                "karma": user_data.get("karma", 0),
                "about": user_data.get("about", "No bio available"),
                "submitted_count": len(user_data.get("submitted", [])),
                "submitted_items": user_data.get("submitted", [])[
                    :10
                ],  # Show first 10 submissions
            }

            # Create formatted text response
            created_date = "N/A"
            if user_info["created"] != "N/A":
                import datetime

                created_date = datetime.datetime.fromtimestamp(
                    user_info["created"]
                ).strftime("%Y-%m-%d %H:%M:%S")

            text_response = f"""**Hacker News User: {user_info['username']}**

**Account Info:**
- Created: {created_date}
- Karma: {user_info['karma']}
- Total Submissions: {user_info['submitted_count']}

**About:**
{user_info['about']}

**Recent Submissions (Item IDs):**
{', '.join(map(str, user_info['submitted_items'])) if user_info['submitted_items'] else 'None'}
"""

            yield self.create_text_message(text_response)
            yield self.create_json_message(user_info)

        except requests.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")
