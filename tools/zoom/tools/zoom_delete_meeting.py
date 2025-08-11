import json
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class ZoomDeleteMeetingTool(Tool):
    """
    Tool for deleting Zoom meetings using OAuth authentication.
    """

    def _invoke(
        self, tool_parameters: dict
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Delete a Zoom meeting by meeting ID.

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
        schedule_for_reminder = tool_parameters.get("schedule_for_reminder", False)
        cancel_meeting_reminder = tool_parameters.get("cancel_meeting_reminder", False)

        # 2. CREDENTIAL HANDLING (OAuth)
        if "access_token" not in self.runtime.credentials:
            yield self.create_text_message(
                "Zoom access token is required. Please authenticate with Zoom first."
            )
            return

        access_token = self.runtime.credentials.get("access_token")

        # 3. LOG THE OPERATION START
        yield self.create_log_message(
            label="Deleting Zoom Meeting",
            data={
                "meeting_id": meeting_id,
                "occurrence_id": occurrence_id,
                "schedule_for_reminder": schedule_for_reminder,
                "cancel_meeting_reminder": cancel_meeting_reminder,
            },
            status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
        )

        try:
            # 4. FIRST, GET MEETING INFO TO SHOW WHAT'S BEING DELETED
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            # Get meeting info first
            get_response = requests.get(
                f"https://api.zoom.us/v2/meetings/{meeting_id}",
                headers=headers,
                timeout=30,
            )

            meeting_info = None
            if get_response.status_code == 200:
                meeting_info = get_response.json()

            # 5. PREPARE DELETE REQUEST
            url = f"https://api.zoom.us/v2/meetings/{meeting_id}"
            params = {}

            if occurrence_id:
                params["occurrence_id"] = occurrence_id

            if schedule_for_reminder:
                params["schedule_for_reminder"] = "true"

            if cancel_meeting_reminder:
                params["cancel_meeting_reminder"] = "true"

            # 6. MAKE API CALL TO DELETE MEETING
            response = requests.delete(url, headers=headers, params=params, timeout=30)

            # 7. HANDLE API RESPONSE
            if response.status_code == 204:  # Success - No Content
                # Success response
                success_message = "✅ Zoom meeting deleted successfully!"

                if meeting_info:
                    success_message += f"""

📋 **Deleted Meeting Details:**
- **Topic:** {meeting_info.get('topic')}
- **Meeting ID:** {meeting_info.get('id')}
- **Type:** {self._get_meeting_type_name(meeting_info.get('type'))}
- **Status:** {meeting_info.get('status')}"""

                    if meeting_info.get("start_time"):
                        success_message += (
                            f"\n- **Scheduled Time:** {meeting_info.get('start_time')}"
                        )

                    if occurrence_id:
                        success_message += f"\n- **Occurrence ID:** {occurrence_id}"

                if occurrence_id:
                    success_message += "\n\n🗓️ **Note:** Only the specific occurrence was deleted. Other occurrences remain active."
                else:
                    success_message += "\n\n🗑️ **Note:** The entire meeting has been permanently deleted."

                # Return structured data
                result_data = {
                    "success": True,
                    "meeting_id": meeting_id,
                    "occurrence_id": occurrence_id,
                    "deleted_meeting": meeting_info,
                    "deletion_type": (
                        "occurrence" if occurrence_id else "entire_meeting"
                    ),
                }

                yield self.create_json_message(result_data)
                yield self.create_text_message(success_message)

            elif response.status_code == 404:
                yield self.create_text_message(
                    f"❌ Meeting not found with ID: {meeting_id}"
                )
                if occurrence_id:
                    yield self.create_text_message(
                        "💡 The occurrence ID might be invalid or the occurrence may have already been deleted."
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
                yield self.create_text_message(f"❌ Cannot delete meeting: {error_msg}")
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
