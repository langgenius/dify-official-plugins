import json
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class ZoomListMeetingsTool(Tool):
    """
    Tool for listing Zoom meetings for the authenticated user using OAuth authentication.
    """

    def _invoke(
        self, tool_parameters: dict
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        List Zoom meetings for the authenticated user.

        Args:
            tool_parameters: Dictionary containing filtering and pagination parameters

        Yields:
            ToolInvokeMessage: Various message types to communicate results
        """
        # 1. PARAMETER EXTRACTION AND VALIDATION
        meeting_type = tool_parameters.get("type", "scheduled")
        page_size = tool_parameters.get("page_size", 30)
        page_number = tool_parameters.get("page_number", 1)
        from_date = tool_parameters.get("from_date")
        to_date = tool_parameters.get("to_date")

        # 2. CREDENTIAL HANDLING (OAuth)
        if "access_token" not in self.runtime.credentials:
            yield self.create_text_message(
                "Zoom access token is required. Please authenticate with Zoom first."
            )
            return

        access_token = self.runtime.credentials.get("access_token")

        # 3. LOG THE OPERATION START
        yield self.create_log_message(
            label="Listing Zoom Meetings",
            data={
                "type": meeting_type,
                "page_size": page_size,
                "page_number": page_number,
                "from_date": from_date,
                "to_date": to_date,
            },
            status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
        )

        try:
            # 4. PREPARE API REQUEST
            url = "https://api.zoom.us/v2/users/me/meetings"
            params = {
                "type": meeting_type,
                "page_size": min(page_size, 300),  # Max 300 per API docs
                "page_number": page_number,
            }

            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            # 5. MAKE API CALL TO LIST MEETINGS
            response = requests.get(url, headers=headers, params=params, timeout=30)

            # 6. HANDLE API RESPONSE
            if response.status_code == 200:
                meetings_data = response.json()
                meetings = meetings_data.get("meetings", [])
                total_records = meetings_data.get("total_records", 0)
                page_count = meetings_data.get("page_count", 0)
                page_size_actual = meetings_data.get("page_size", 0)

                # Extract essential information for each meeting
                meetings_list = []
                for meeting in meetings:
                    meeting_info = {
                        "meeting_id": meeting.get("id"),
                        "uuid": meeting.get("uuid"),
                        "topic": meeting.get("topic"),
                        "type": meeting.get("type"),
                        "status": meeting.get("status"),
                        "start_time": meeting.get("start_time"),
                        "duration": meeting.get("duration"),
                        "timezone": meeting.get("timezone"),
                        "join_url": meeting.get("join_url"),
                        "created_at": meeting.get("created_at"),
                        "host_email": meeting.get("host_email"),
                    }
                    meetings_list.append(meeting_info)

                # Return structured data
                result_data = {
                    "meetings": meetings_list,
                    "pagination": {
                        "page_count": page_count,
                        "page_number": page_number,
                        "page_size": page_size_actual,
                        "total_records": total_records,
                    },
                    "filters": {
                        "type": meeting_type,
                        "from_date": from_date,
                        "to_date": to_date,
                    },
                }

                yield self.create_json_message(result_data)

                # Create user-friendly summary
                meeting_type_names = {
                    "scheduled": "Scheduled",
                    "live": "Live",
                    "upcoming": "Upcoming",
                    "upcoming_meetings": "Upcoming",
                    "previous_meetings": "Previous",
                }

                status_names = {
                    "waiting": "⏳ Waiting",
                    "started": "🟢 Started",
                    "finished": "✅ Finished",
                }

                type_display = meeting_type_names.get(
                    meeting_type, meeting_type.title()
                )

                summary = f"""📋 **{type_display} Meetings**

**Summary:**
- **Total Meetings:** {total_records}
- **Showing:** Page {page_number} of {page_count} ({len(meetings)} meetings)
- **Page Size:** {page_size_actual}"""

                if from_date or to_date:
                    summary += f"\n- **Date Range:** {from_date or 'Start'} to {to_date or 'End'}"

                if meetings:
                    summary += f"\n\n**Meetings:**"

                    for i, meeting in enumerate(meetings[:10]):  # Show first 10
                        meeting_type_num = meeting.get("type")
                        type_display_individual = {
                            1: "Instant",
                            2: "Scheduled",
                            3: "Recurring (No Fixed Time)",
                            8: "Recurring (Fixed Time)",
                        }.get(meeting_type_num, "Unknown")

                        status_display = status_names.get(
                            meeting.get("status"), meeting.get("status", "Unknown")
                        )

                        summary += f"""
**{i+1}. {meeting.get('topic', 'Untitled')}**
- ID: {meeting.get('id')}
- Type: {type_display_individual}
- Status: {status_display}
- Start: {meeting.get('start_time', 'Not scheduled')}
- Duration: {meeting.get('duration', 'N/A')} min"""

                        if meeting.get("join_url"):
                            summary += f"\n- Join: {meeting.get('join_url')}"

                    if len(meetings) > 10:
                        summary += f"\n\n... and {len(meetings) - 10} more meetings"

                    # Pagination info
                    if page_count > 1:
                        summary += f"\n\n**Pagination:**"
                        if page_number > 1:
                            summary += f"\n- Previous page: {page_number - 1}"
                        if page_number < page_count:
                            summary += f"\n- Next page: {page_number + 1}"
                        summary += f"\n- Total pages: {page_count}"
                else:
                    summary += f"\n\n❌ No meetings found for the specified criteria."

                yield self.create_text_message(summary)

                # Provide join URLs for upcoming meetings
                upcoming_meetings = [
                    m
                    for m in meetings
                    if m.get("status") == "waiting" and m.get("join_url")
                ]
                if upcoming_meetings:
                    yield self.create_text_message(
                        "🔗 **Quick Join Links for Upcoming Meetings:**"
                    )
                    for meeting in upcoming_meetings[:5]:  # Show first 5
                        yield self.create_link_message(meeting["join_url"])

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
