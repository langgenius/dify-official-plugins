import json
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class ZoomGetMeetingTool(Tool):
    """
    Tool for retrieving Zoom meeting information by meeting ID using OAuth authentication.
    """

    def _invoke(
        self, tool_parameters: dict
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get Zoom meeting information by meeting ID.

        Args:
            tool_parameters: Dictionary containing meeting ID and optional parameters

        Yields:
            ToolInvokeMessage: Various message types to communicate results
        """
        # 1. PARAMETER EXTRACTION AND VALIDATION
        meeting_id = tool_parameters.get("meeting_id")
        if not meeting_id:
            yield self.create_text_message("Meeting ID is required.")
            return

        # Extract optional parameters
        occurrence_id = tool_parameters.get("occurrence_id")
        show_previous_occurrences = tool_parameters.get(
            "show_previous_occurrences", False
        )

        # 2. CREDENTIAL HANDLING (OAuth)
        if "access_token" not in self.runtime.credentials:
            yield self.create_text_message(
                "Zoom access token is required. Please authenticate with Zoom first."
            )
            return

        access_token = self.runtime.credentials.get("access_token")

        # 3. LOG THE OPERATION START
        yield self.create_log_message(
            label="Getting Zoom Meeting Info",
            data={
                "meeting_id": meeting_id,
                "occurrence_id": occurrence_id,
                "show_previous_occurrences": show_previous_occurrences,
            },
            status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
        )

        try:
            # 4. PREPARE API REQUEST
            url = f"https://api.zoom.us/v2/meetings/{meeting_id}"
            params = {}

            if occurrence_id:
                params["occurrence_id"] = occurrence_id

            if show_previous_occurrences:
                params["show_previous_occurrences"] = "true"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            # 5. MAKE API CALL TO GET MEETING INFO
            response = requests.get(url, headers=headers, params=params, timeout=30)

            # 6. HANDLE API RESPONSE
            if response.status_code == 200:
                meeting_info = response.json()

                # Extract key meeting information
                meeting_result = {
                    "meeting_id": meeting_info.get("id"),
                    "uuid": meeting_info.get("uuid"),
                    "host_id": meeting_info.get("host_id"),
                    "host_email": meeting_info.get("host_email"),
                    "topic": meeting_info.get("topic"),
                    "type": meeting_info.get("type"),
                    "status": meeting_info.get("status"),
                    "start_time": meeting_info.get("start_time"),
                    "duration": meeting_info.get("duration"),
                    "timezone": meeting_info.get("timezone"),
                    "agenda": meeting_info.get("agenda"),
                    "created_at": meeting_info.get("created_at"),
                    "start_url": meeting_info.get("start_url"),
                    "join_url": meeting_info.get("join_url"),
                    "password": meeting_info.get("password"),
                    "encrypted_password": meeting_info.get("encrypted_password"),
                    "pmi": meeting_info.get("pmi"),
                    "tracking_fields": meeting_info.get("tracking_fields"),
                    "occurrences": meeting_info.get("occurrences"),
                    "settings": meeting_info.get("settings"),
                }

                # Return structured data
                yield self.create_json_message(meeting_result)

                # Create user-friendly summary
                meeting_type_names = {
                    1: "Instant Meeting",
                    2: "Scheduled Meeting",
                    3: "Recurring (No Fixed Time)",
                    8: "Recurring (Fixed Time)",
                }

                status_names = {
                    "waiting": "⏳ Waiting",
                    "started": "🟢 Started",
                    "finished": "✅ Finished",
                }

                meeting_type_display = meeting_type_names.get(
                    meeting_info.get("type"), "Unknown"
                )
                status_display = status_names.get(
                    meeting_info.get("status"), meeting_info.get("status", "Unknown")
                )

                summary = f"""📋 **Meeting Information**

**Basic Details:**
- **Topic:** {meeting_info.get('topic')}
- **Meeting ID:** {meeting_info.get('id')}
- **Type:** {meeting_type_display}
- **Status:** {status_display}
- **Host Email:** {meeting_info.get('host_email')}

**Schedule:**
- **Start Time:** {meeting_info.get('start_time', 'Not scheduled')}
- **Duration:** {meeting_info.get('duration')} minutes
- **Timezone:** {meeting_info.get('timezone', 'Not specified')}

**Access:**
- **Join URL:** {meeting_info.get('join_url', 'Not available')}
- **Password:** {meeting_info.get('password', 'Not set')}
- **PMI:** {meeting_info.get('pmi', 'Not applicable')}"""

                if meeting_info.get("agenda"):
                    summary += f"\n\n**Agenda:**\n{meeting_info.get('agenda')}"

                # Add settings information if available
                settings = meeting_info.get("settings", {})
                if settings:
                    summary += f"\n\n**Settings:**"
                    if "waiting_room" in settings:
                        summary += f"\n- Waiting Room: {'✅' if settings['waiting_room'] else '❌'}"
                    if "join_before_host" in settings:
                        summary += f"\n- Join Before Host: {'✅' if settings['join_before_host'] else '❌'}"
                    if "mute_upon_entry" in settings:
                        summary += f"\n- Mute Upon Entry: {'✅' if settings['mute_upon_entry'] else '❌'}"
                    if "auto_recording" in settings:
                        summary += f"\n- Auto Recording: {settings['auto_recording']}"

                # Add occurrences if it's a recurring meeting
                occurrences = meeting_info.get("occurrences", [])
                if occurrences:
                    summary += f"\n\n**Upcoming Occurrences:**"
                    for i, occurrence in enumerate(occurrences[:5]):  # Show first 5
                        summary += f"\n- {occurrence.get('start_time')} (ID: {occurrence.get('occurrence_id')})"
                    if len(occurrences) > 5:
                        summary += f"\n- ... and {len(occurrences) - 5} more"

                yield self.create_text_message(summary)

                # Provide the join URL as a clickable link if available
                if meeting_info.get("join_url"):
                    yield self.create_link_message(meeting_info["join_url"])

            elif response.status_code == 404:
                yield self.create_text_message(
                    f"❌ Meeting not found with ID: {meeting_id}"
                )
                yield self.create_json_message(
                    {"error": "Meeting not found", "meeting_id": meeting_id}
                )

            elif response.status_code == 401:
                yield self.create_text_message(
                    "❌ Unauthorized: Please re-authenticate with Zoom. Your access token may have expired."
                )

            else:
                error_data = (
                    response.json()
                    if response.headers.get("content-type") == "application/json"
                    else {}
                )
                error_msg = error_data.get(
                    "message", f"API request failed with status {response.status_code}"
                )
                yield self.create_text_message(f"❌ {error_msg}")
                yield self.create_json_message(
                    {"error": error_msg, "status_code": response.status_code}
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
