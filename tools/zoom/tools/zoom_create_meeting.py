import json
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class ZoomCreateMeetingTool(Tool):
    """
    Tool for creating Zoom meetings with various configuration options using OAuth authentication.
    """

    def _invoke(
        self, tool_parameters: dict
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a new Zoom meeting with specified parameters.

        Args:
            tool_parameters: Dictionary containing meeting configuration parameters

        Yields:
            ToolInvokeMessage: Various message types to communicate results
        """
        # 1. PARAMETER EXTRACTION AND VALIDATION
        topic = tool_parameters.get("topic")
        if not topic:
            yield self.create_text_message("Meeting topic is required.")
            return

        # Extract other parameters with defaults
        meeting_type = tool_parameters.get("type", 2)  # 2 = Scheduled meeting
        start_time = tool_parameters.get("start_time")
        duration = tool_parameters.get("duration", 60)
        password = tool_parameters.get("password", "")
        waiting_room = tool_parameters.get("waiting_room", True)
        join_before_host = tool_parameters.get("join_before_host", False)
        mute_upon_entry = tool_parameters.get("mute_upon_entry", True)
        auto_recording = tool_parameters.get("auto_recording", "none")
        timezone_param = tool_parameters.get("timezone", "UTC")
        agenda = tool_parameters.get("agenda", "")

        # 2. CREDENTIAL HANDLING (OAuth)
        if "access_token" not in self.runtime.credentials:
            yield self.create_text_message(
                "Zoom access token is required. Please authenticate with Zoom first."
            )
            return

        access_token = self.runtime.credentials.get("access_token")

        # 3. LOG THE OPERATION START
        yield self.create_log_message(
            label="Creating Zoom Meeting",
            data={
                "topic": topic,
                "type": meeting_type,
                "duration": duration,
                "start_time": start_time,
            },
            status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
        )

        try:
            # 4. PREPARE MEETING DATA
            meeting_data = {
                "topic": topic,
                "type": meeting_type,
                "duration": duration,
                "settings": {
                    "waiting_room": waiting_room,
                    "join_before_host": join_before_host,
                    "mute_upon_entry": mute_upon_entry,
                    "auto_recording": auto_recording,
                },
            }

            # Add optional parameters
            if start_time:
                meeting_data["start_time"] = start_time
                meeting_data["timezone"] = timezone_param

            if password:
                meeting_data["password"] = password

            if agenda:
                meeting_data["agenda"] = agenda

            # 5. MAKE API CALL TO CREATE MEETING
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            response = requests.post(
                "https://api.zoom.us/v2/users/me/meetings",
                headers=headers,
                json=meeting_data,
                timeout=30,
            )

            # 6. HANDLE API RESPONSE
            if response.status_code == 201:
                meeting_info = response.json()

                # Extract key meeting information
                meeting_result = {
                    "meeting_id": meeting_info.get("id"),
                    "topic": meeting_info.get("topic"),
                    "start_url": meeting_info.get("start_url"),
                    "join_url": meeting_info.get("join_url"),
                    "password": meeting_info.get("password"),
                    "start_time": meeting_info.get("start_time"),
                    "duration": meeting_info.get("duration"),
                    "timezone": meeting_info.get("timezone"),
                    "status": meeting_info.get("status"),
                    "created_at": meeting_info.get("created_at"),
                }

                # Return structured data
                yield self.create_json_message(meeting_result)

                # Create user-friendly summary
                summary = f"""✅ Zoom meeting created successfully!

📋 **Meeting Details:**
- **Topic:** {meeting_info.get('topic')}
- **Meeting ID:** {meeting_info.get('id')}
- **Duration:** {meeting_info.get('duration')} minutes
- **Password:** {meeting_info.get('password', 'None')}

🔗 **Links:**
- **Start URL (Host):** {meeting_info.get('start_url')}
- **Join URL (Participants):** {meeting_info.get('join_url')}

⏰ **Schedule:**
- **Start Time:** {meeting_info.get('start_time', 'Instant meeting')}
- **Timezone:** {meeting_info.get('timezone', 'N/A')}"""

                yield self.create_text_message(summary)

                # Provide the join URL as a clickable link
                if meeting_info.get("join_url"):
                    yield self.create_link_message(meeting_info["join_url"])

            elif response.status_code == 400:
                error_data = response.json()
                error_msg = error_data.get("message", "Bad request")
                yield self.create_text_message(
                    f"❌ Failed to create meeting: {error_msg}"
                )
                yield self.create_json_message(
                    {"error": error_msg, "code": error_data.get("code")}
                )

            elif response.status_code == 401:
                yield self.create_text_message(
                    "❌ Unauthorized: Please re-authenticate with Zoom. Your access token may have expired."
                )

            else:
                yield self.create_text_message(
                    f"❌ API request failed with status {response.status_code}: {response.text}"
                )

        except requests.Timeout:
            yield self.create_text_message("❌ Request timed out. Please try again.")

        except requests.RequestException as e:
            yield self.create_log_message(
                label="Network Error",
                data={"error": str(e)},
                status=InvokeMessage.LogMessage.LogStatus.ERROR,
            )
            yield self.create_text_message(f"❌ Network error occurred: {str(e)}")

        except Exception as e:
            yield self.create_log_message(
                label="Unexpected Error",
                data={"error": str(e), "type": type(e).__name__},
                status=InvokeMessage.LogMessage.LogStatus.ERROR,
            )
            yield self.create_text_message(f"❌ An unexpected error occurred: {str(e)}")
