import json
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class ZoomUpdateMeetingTool(Tool):
    """
    Tool for updating Zoom meetings using OAuth authentication.
    """

    def _invoke(
        self, tool_parameters: dict
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Update a Zoom meeting with new settings.

        Args:
            tool_parameters: Dictionary containing meeting ID and update parameters

        Yields:
            ToolInvokeMessage: Various message types to communicate results
        """
        # 1. PARAMETER EXTRACTION AND VALIDATION
        meeting_id = tool_parameters.get("meeting_id")
        if not meeting_id:
            yield self.create_text_message("Meeting ID is required.")
            return

        # Extract update parameters
        topic = tool_parameters.get("topic")
        meeting_type = tool_parameters.get("type")
        start_time = tool_parameters.get("start_time")
        duration = tool_parameters.get("duration")
        timezone_param = tool_parameters.get("timezone")
        password = tool_parameters.get("password")
        agenda = tool_parameters.get("agenda")

        # Settings parameters
        waiting_room = tool_parameters.get("waiting_room")
        join_before_host = tool_parameters.get("join_before_host")
        mute_upon_entry = tool_parameters.get("mute_upon_entry")
        auto_recording = tool_parameters.get("auto_recording")

        # Optional parameters
        occurrence_id = tool_parameters.get("occurrence_id")

        # 2. CREDENTIAL HANDLING (OAuth)
        if "access_token" not in self.runtime.credentials:
            yield self.create_text_message(
                "Zoom access token is required. Please authenticate with Zoom first."
            )
            return

        access_token = self.runtime.credentials.get("access_token")

        # 3. LOG THE OPERATION START
        yield self.create_log_message(
            label="Updating Zoom Meeting",
            data={
                "meeting_id": meeting_id,
                "occurrence_id": occurrence_id,
                "updates": {
                    k: v
                    for k, v in tool_parameters.items()
                    if v is not None and k != "meeting_id"
                },
            },
            status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
        )

        try:
            # 4. FIRST, GET CURRENT MEETING INFO
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            get_response = requests.get(
                f"https://api.zoom.us/v2/meetings/{meeting_id}",
                headers=headers,
                timeout=30,
            )

            if get_response.status_code != 200:
                yield self.create_text_message(
                    f"❌ Could not retrieve meeting information: {get_response.status_code}"
                )
                return

            current_meeting = get_response.json()

            # 5. PREPARE UPDATE DATA
            update_data = {}

            # Basic meeting fields
            if topic is not None:
                update_data["topic"] = topic
            if meeting_type is not None:
                update_data["type"] = meeting_type
            if start_time is not None:
                update_data["start_time"] = start_time
            if duration is not None:
                update_data["duration"] = duration
            if timezone_param is not None:
                update_data["timezone"] = timezone_param
            if password is not None:
                update_data["password"] = password
            if agenda is not None:
                update_data["agenda"] = agenda

            # Settings
            settings = {}
            if waiting_room is not None:
                settings["waiting_room"] = waiting_room
            if join_before_host is not None:
                settings["join_before_host"] = join_before_host
            if mute_upon_entry is not None:
                settings["mute_upon_entry"] = mute_upon_entry
            if auto_recording is not None:
                settings["auto_recording"] = auto_recording

            if settings:
                update_data["settings"] = settings

            if not update_data:
                yield self.create_text_message(
                    "❌ No update parameters provided. Please specify at least one field to update."
                )
                return

            # 6. PREPARE API REQUEST
            url = f"https://api.zoom.us/v2/meetings/{meeting_id}"
            params = {}

            if occurrence_id:
                params["occurrence_id"] = occurrence_id

            # 7. MAKE API CALL TO UPDATE MEETING
            response = requests.patch(
                url, headers=headers, params=params, json=update_data, timeout=30
            )

            # 8. HANDLE API RESPONSE
            if response.status_code == 204:  # Success - No Content
                # Get updated meeting info
                updated_response = requests.get(
                    f"https://api.zoom.us/v2/meetings/{meeting_id}",
                    headers=headers,
                    timeout=30,
                )

                updated_meeting = None
                if updated_response.status_code == 200:
                    updated_meeting = updated_response.json()

                # Create success message
                success_message = "✅ Zoom meeting updated successfully!"

                if updated_meeting:
                    success_message += f"""

📋 **Updated Meeting Details:**
- **Topic:** {updated_meeting.get('topic')}
- **Meeting ID:** {updated_meeting.get('id')}
- **Type:** {self._get_meeting_type_name(updated_meeting.get('type'))}
- **Status:** {updated_meeting.get('status')}
- **Duration:** {updated_meeting.get('duration')} minutes"""

                    if updated_meeting.get("start_time"):
                        success_message += (
                            f"\n- **Start Time:** {updated_meeting.get('start_time')}"
                        )

                    if updated_meeting.get("timezone"):
                        success_message += (
                            f"\n- **Timezone:** {updated_meeting.get('timezone')}"
                        )

                    if updated_meeting.get("password"):
                        success_message += (
                            f"\n- **Password:** {updated_meeting.get('password')}"
                        )

                    if occurrence_id:
                        success_message += f"\n- **Occurrence ID:** {occurrence_id}"

                # Show what was changed
                changes = []
                for key, value in update_data.items():
                    if key != "settings":
                        old_value = current_meeting.get(key)
                        if old_value != value:
                            changes.append(f"  - {key}: {old_value} → {value}")

                if "settings" in update_data:
                    current_settings = current_meeting.get("settings", {})
                    for setting_key, setting_value in update_data["settings"].items():
                        old_setting = current_settings.get(setting_key)
                        if old_setting != setting_value:
                            changes.append(
                                f"  - {setting_key}: {old_setting} → {setting_value}"
                            )

                if changes:
                    success_message += f"\n\n🔄 **Changes Made:**\n" + "\n".join(
                        changes
                    )

                if occurrence_id:
                    success_message += (
                        "\n\n🗓️ **Note:** Only the specific occurrence was updated."
                    )

                # Return structured data
                result_data = {
                    "success": True,
                    "meeting_id": meeting_id,
                    "occurrence_id": occurrence_id,
                    "updated_meeting": updated_meeting,
                    "changes_made": update_data,
                    "update_type": "occurrence" if occurrence_id else "entire_meeting",
                }

                yield self.create_json_message(result_data)
                yield self.create_text_message(success_message)

                # Provide join URL if available
                if updated_meeting and updated_meeting.get("join_url"):
                    yield self.create_link_message(updated_meeting["join_url"])

            elif response.status_code == 404:
                yield self.create_text_message(
                    f"❌ Meeting not found with ID: {meeting_id}"
                )
                if occurrence_id:
                    yield self.create_text_message(
                        "💡 The occurrence ID might be invalid."
                    )
                yield self.create_json_message(
                    {"error": "Meeting not found", "meeting_id": meeting_id}
                )

            elif response.status_code == 401:
                yield self.create_text_message(
                    "❌ Unauthorized: Please re-authenticate with Zoom. Your access token may have expired."
                )

            elif response.status_code == 400:
                error_data = (
                    response.json()
                    if response.headers.get("content-type") == "application/json"
                    else {}
                )
                error_msg = error_data.get("message", "Bad request")
                yield self.create_text_message(f"❌ Cannot update meeting: {error_msg}")
                yield self.create_json_message(
                    {"error": error_msg, "code": error_data.get("code")}
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

    def _get_meeting_type_name(self, meeting_type: int) -> str:
        """Helper method to get human-readable meeting type name"""
        type_names = {
            1: "Instant Meeting",
            2: "Scheduled Meeting",
            3: "Recurring (No Fixed Time)",
            8: "Recurring (Fixed Time)",
        }
        return type_names.get(meeting_type, "Unknown")
