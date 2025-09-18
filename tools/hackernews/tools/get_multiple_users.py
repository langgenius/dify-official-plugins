import datetime
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class GetMultipleUsersTool(Tool):
    """
    Tool for retrieving information about multiple Hacker News users.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get information about multiple Hacker News users.
        """
        # Extract parameters
        usernames = tool_parameters.get("usernames", "")
        include_submissions = tool_parameters.get("include_submissions", False)
        max_submissions = tool_parameters.get("max_submissions", 5)

        if not usernames:
            yield self.create_text_message("Usernames are required")
            return

        # Parse usernames - handle both comma-separated string and list
        if isinstance(usernames, str):
            username_list = [u.strip() for u in usernames.split(",") if u.strip()]
        elif isinstance(usernames, list):
            username_list = [str(u).strip() for u in usernames if str(u).strip()]
        else:
            yield self.create_text_message("Invalid usernames format")
            return

        if not username_list:
            yield self.create_text_message("No valid usernames provided")
            return

        if len(username_list) > 10:
            yield self.create_text_message("Maximum 10 users can be fetched at once")
            return

        try:
            # Log the operation start
            yield self.create_log_message(
                label="Fetching Multiple Users",
                data={"usernames": username_list, "count": len(username_list)},
                status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
            )

            users_data = []
            failed_users = []

            for i, username in enumerate(username_list):
                try:
                    # Show progress
                    yield self.create_log_message(
                        label=f"Fetching User {i+1}/{len(username_list)}",
                        data={"username": username},
                        status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
                    )

                    # Make API call to get user info
                    api_url = (
                        f"https://hacker-news.firebaseio.com/v0/user/{username}.json"
                    )
                    response = requests.get(api_url, timeout=10)

                    if response.status_code == 404:
                        failed_users.append(
                            {"username": username, "error": "User not found"}
                        )
                        continue

                    if response.status_code != 200:
                        failed_users.append(
                            {
                                "username": username,
                                "error": f"HTTP {response.status_code}",
                            }
                        )
                        continue

                    user_data = response.json()

                    if not user_data:
                        failed_users.append(
                            {"username": username, "error": "User not found"}
                        )
                        continue

                    # Format user information
                    created_date = "N/A"
                    if user_data.get("created"):
                        created_date = datetime.datetime.fromtimestamp(
                            user_data["created"]
                        ).strftime("%Y-%m-%d %H:%M:%S")

                    user_info = {
                        "username": user_data.get("id", username),
                        "created": user_data.get("created"),
                        "created_formatted": created_date,
                        "karma": user_data.get("karma", 0),
                        "about": user_data.get("about", "No bio available"),
                        "submitted_count": len(user_data.get("submitted", [])),
                        "submitted_items": (
                            user_data.get("submitted", [])[:max_submissions]
                            if include_submissions
                            else []
                        ),
                    }

                    # Get submission details if requested
                    if include_submissions and user_info["submitted_items"]:
                        submissions = []
                        for submission_id in user_info["submitted_items"]:
                            try:
                                sub_response = requests.get(
                                    f"https://hacker-news.firebaseio.com/v0/item/{submission_id}.json",
                                    timeout=5,
                                )
                                if sub_response.status_code == 200:
                                    sub_data = sub_response.json()
                                    if sub_data:
                                        sub_created = "N/A"
                                        if sub_data.get("time"):
                                            sub_created = (
                                                datetime.datetime.fromtimestamp(
                                                    sub_data["time"]
                                                ).strftime("%Y-%m-%d %H:%M")
                                            )

                                        submissions.append(
                                            {
                                                "id": sub_data.get("id"),
                                                "title": sub_data.get(
                                                    "title", "No title"
                                                ),
                                                "type": sub_data.get("type", "unknown"),
                                                "score": sub_data.get("score", 0),
                                                "created": sub_created,
                                                "url": sub_data.get("url", ""),
                                                "descendants": sub_data.get(
                                                    "descendants", 0
                                                ),
                                            }
                                        )
                            except:
                                continue
                        user_info["submission_details"] = submissions

                    users_data.append(user_info)

                except requests.RequestException as e:
                    failed_users.append(
                        {"username": username, "error": f"Network error: {str(e)}"}
                    )
                except Exception as e:
                    failed_users.append(
                        {"username": username, "error": f"Error: {str(e)}"}
                    )

            # Create formatted text response
            text_response = f"**Hacker News Users Information ({len(users_data)} of {len(username_list)} found)**\n\n"

            for i, user in enumerate(users_data, 1):
                text_response += f"**{i}. {user['username']}**\n"
                text_response += f"   • Created: {user['created_formatted']}\n"
                text_response += f"   • Karma: {user['karma']}\n"
                text_response += f"   • Submissions: {user['submitted_count']}\n"

                if user["about"] and user["about"] != "No bio available":
                    about_text = (
                        user["about"][:100] + "..."
                        if len(user["about"]) > 100
                        else user["about"]
                    )
                    text_response += f"   • About: {about_text}\n"

                if include_submissions and user.get("submission_details"):
                    text_response += f"   • Recent Submissions:\n"
                    for sub in user["submission_details"]:
                        text_response += f"     - {sub['title']} (ID: {sub['id']}, Score: {sub['score']})\n"

                text_response += "\n"

            if failed_users:
                text_response += "**Failed to fetch:**\n"
                for failed in failed_users:
                    text_response += f"• {failed['username']}: {failed['error']}\n"

            yield self.create_text_message(text_response)
            yield self.create_json_message(
                {
                    "total_requested": len(username_list),
                    "successfully_fetched": len(users_data),
                    "failed_count": len(failed_users),
                    "users": users_data,
                    "failed_users": failed_users,
                }
            )

        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")
