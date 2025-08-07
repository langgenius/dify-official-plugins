from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class ListCalendarsTool(Tool):
    """
    List all calendars accessible to the user.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        List all calendars for the authenticated user.
        """
        # Check if credentials are available
        if "access_token" not in self.runtime.credentials:
            yield self.create_text_message(
                "Google Calendar access token is required. Please configure OAuth authentication."
            )
            return

        access_token = self.runtime.credentials.get("access_token")

        # Start operation log
        operation_log = self.create_log_message(
            label="List Calendars Operation",
            data={"operation": "list_calendars"},
            status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
        )
        yield operation_log

        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }

            # Make API call to list calendars
            api_log = self.create_log_message(
                label="API Call",
                data={
                    "endpoint": "https://www.googleapis.com/calendar/v3/users/me/calendarList"
                },
                status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
                parent=operation_log,
            )
            yield api_log

            response = requests.get(
                "https://www.googleapis.com/calendar/v3/users/me/calendarList",
                headers=headers,
                timeout=30,
            )

            if response.status_code == 200:
                calendar_data = response.json()
                calendars = calendar_data.get("items", [])

                # Format calendar data for output
                calendar_list = []
                for calendar in calendars:
                    calendar_info = {
                        "id": calendar.get("id"),
                        "summary": calendar.get("summary"),
                        "description": calendar.get("description", ""),
                        "primary": calendar.get("primary", False),
                        "access_role": calendar.get("accessRole"),
                        "time_zone": calendar.get("timeZone"),
                        "background_color": calendar.get("backgroundColor"),
                        "foreground_color": calendar.get("foregroundColor"),
                        "selected": calendar.get("selected", False),
                    }
                    calendar_list.append(calendar_info)

                # Return structured data
                result = {
                    "success": True,
                    "message": f"Found {len(calendar_list)} calendars",
                    "calendars": calendar_list,
                    "total_count": len(calendar_list),
                }

                yield self.create_json_message(result)

                # Create a user-friendly text summary
                if calendar_list:
                    summary_text = f"Found {len(calendar_list)} calendars:\n\n"
                    for cal in calendar_list:
                        primary_mark = " (Primary)" if cal.get("primary") else ""
                        summary_text += f"• {cal.get('summary', 'Unnamed Calendar')}{primary_mark}\n"
                        summary_text += f"  ID: {cal.get('id')}\n"
                        summary_text += (
                            f"  Access: {cal.get('access_role', 'Unknown')}\n"
                        )
                        if cal.get("description"):
                            summary_text += f"  Description: {cal.get('description')}\n"
                        summary_text += (
                            f"  Time Zone: {cal.get('time_zone', 'Unknown')}\n\n"
                        )

                    yield self.create_text_message(summary_text)
                else:
                    yield self.create_text_message("No calendars found.")

            elif response.status_code == 401:
                yield self.create_log_message(
                    label="Authentication Error",
                    data={
                        "status_code": response.status_code,
                        "error": "Invalid or expired token",
                    },
                    status=InvokeMessage.LogMessage.LogStatus.ERROR,
                )
                yield self.create_text_message(
                    "Authentication failed. Please re-authenticate with Google Calendar."
                )

            elif response.status_code == 403:
                yield self.create_log_message(
                    label="Permission Error",
                    data={
                        "status_code": response.status_code,
                        "error": "Insufficient permissions",
                    },
                    status=InvokeMessage.LogMessage.LogStatus.ERROR,
                )
                yield self.create_text_message(
                    "Insufficient permissions. Please ensure Calendar API access is granted."
                )

            else:
                error_msg = f"API request failed with status {response.status_code}"
                yield self.create_log_message(
                    label="API Error",
                    data={
                        "status_code": response.status_code,
                        "error": response.text[:200],
                    },
                    status=InvokeMessage.LogMessage.LogStatus.ERROR,
                )
                yield self.create_text_message(error_msg)

        except requests.Timeout:
            yield self.create_text_message("Request timed out. Please try again.")
        except requests.RequestException as e:
            yield self.create_log_message(
                label="Network Error",
                data={"error": str(e)},
                status=InvokeMessage.LogMessage.LogStatus.ERROR,
            )
            yield self.create_text_message(f"Network error occurred: {str(e)}")
        except Exception as e:
            yield self.create_log_message(
                label="Unexpected Error",
                data={"error": str(e), "type": type(e).__name__},
                status=InvokeMessage.LogMessage.LogStatus.ERROR,
            )
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}")
