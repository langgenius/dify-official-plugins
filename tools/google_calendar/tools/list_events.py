import re
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class ListEventsTool(Tool):
    """
    List events from a specific calendar within a date range.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        List events from a calendar with optional date filtering.
        """
        # Check if credentials are available
        if "access_token" not in self.runtime.credentials:
            yield self.create_text_message(
                "Google Calendar access token is required. Please configure OAuth authentication."
            )
            return

        # Extract parameters
        calendar_id = tool_parameters.get("calendar_id", "primary")
        time_min = tool_parameters.get("time_min")
        time_max = tool_parameters.get("time_max")
        max_results = tool_parameters.get("max_results", 10)
        show_deleted = tool_parameters.get("show_deleted", False)
        single_events = tool_parameters.get("single_events", True)
        order_by = tool_parameters.get("order_by", "startTime")

        access_token = self.runtime.credentials.get("access_token")

        # Start operation log
        operation_log = self.create_log_message(
            label="List Events Operation",
            data={
                "calendar_id": calendar_id,
                "time_min": time_min,
                "time_max": time_max,
                "max_results": max_results,
            },
            status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
        )
        yield operation_log

        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }

            # Build query parameters
            params = {
                "maxResults": max_results,
                "singleEvents": str(single_events).lower(),
                "orderBy": order_by if single_events else None,
                "showDeleted": str(show_deleted).lower(),
            }

            # Add time filters if provided
            if time_min:
                params["timeMin"] = self._format_datetime(time_min)
            if time_max:
                params["timeMax"] = self._format_datetime(time_max)

            # Remove None values
            params = {k: v for k, v in params.items() if v is not None}

            # Make API call
            api_url = (
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
            )

            api_log = self.create_log_message(
                label="API Call",
                data={"endpoint": api_url, "params": params},
                status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
                parent=operation_log,
            )
            yield api_log

            response = requests.get(api_url, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                events_data = response.json()
                events = events_data.get("items", [])

                # Format event data
                formatted_events = []
                for event in events:
                    event_info = self._format_event(event)
                    formatted_events.append(event_info)

                # Return structured data
                result = {
                    "success": True,
                    "message": f"Found {len(formatted_events)} events in calendar",
                    "events": formatted_events,
                    "total_count": len(formatted_events),
                    "calendar_id": calendar_id,
                    "next_page_token": events_data.get("nextPageToken"),
                    "time_zone": events_data.get("timeZone"),
                }

                yield self.create_json_message(result)

                # Create user-friendly text summary
                if formatted_events:
                    summary_text = f"Found {len(formatted_events)} events in calendar '{calendar_id}':\n\n"

                    for event in formatted_events:
                        summary_text += f"📅 {event.get('title', 'Untitled Event')}\n"

                        # Add time information
                        start_time = event.get("start_time")
                        end_time = event.get("end_time")
                        if start_time and end_time:
                            summary_text += f"   🕒 {start_time} - {end_time}\n"
                        elif start_time:
                            summary_text += f"   🕒 {start_time}\n"

                        # Add description if available
                        if event.get("description"):
                            desc = (
                                event["description"][:100] + "..."
                                if len(event.get("description", "")) > 100
                                else event["description"]
                            )
                            summary_text += f"   📝 {desc}\n"

                        # Add location if available
                        if event.get("location"):
                            summary_text += f"   📍 {event['location']}\n"

                        # Add attendees if available
                        attendees = event.get("attendees", [])
                        if attendees:
                            attendee_names = [
                                a.get("email", "Unknown") for a in attendees[:3]
                            ]
                            summary_text += f"   👥 {', '.join(attendee_names)}"
                            if len(attendees) > 3:
                                summary_text += f" and {len(attendees) - 3} more"
                            summary_text += "\n"

                        summary_text += "\n"

                    yield self.create_text_message(summary_text)
                else:
                    yield self.create_text_message(
                        "No events found in the specified calendar and time range."
                    )

            elif response.status_code == 401:
                yield self.create_log_message(
                    label="Authentication Error",
                    data={"status_code": response.status_code},
                    status=InvokeMessage.LogMessage.LogStatus.ERROR,
                )
                yield self.create_text_message(
                    "Authentication failed. Please re-authenticate with Google Calendar."
                )

            elif response.status_code == 403:
                yield self.create_log_message(
                    label="Permission Error",
                    data={"status_code": response.status_code},
                    status=InvokeMessage.LogMessage.LogStatus.ERROR,
                )
                yield self.create_text_message(
                    "Insufficient permissions to access this calendar."
                )

            elif response.status_code == 404:
                yield self.create_log_message(
                    label="Calendar Not Found",
                    data={
                        "status_code": response.status_code,
                        "calendar_id": calendar_id,
                    },
                    status=InvokeMessage.LogMessage.LogStatus.ERROR,
                )
                yield self.create_text_message(
                    f"Calendar '{calendar_id}' not found or not accessible."
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

    def _format_datetime(self, dt_string: str) -> str:
        """
        Format datetime string to RFC3339 format expected by Google Calendar API.
        Accepts various formats like ISO 8601, natural language dates, etc.
        """
        try:
            # If it's already in RFC3339 format, return as is
            if re.match(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2}|Z)",
                dt_string,
            ):
                return dt_string

            # Try parsing common formats
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
                try:
                    dt = datetime.strptime(dt_string, fmt)
                    # Add timezone if not present
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.isoformat()
                except ValueError:
                    continue

            # If no format matches, return as is (let API handle the error)
            return dt_string

        except Exception:
            return dt_string

    def _format_event(self, event: dict) -> dict:
        """
        Format a single event for consistent output.
        """
        try:
            # Extract start and end times
            start = event.get("start", {})
            end = event.get("end", {})

            start_time = None
            end_time = None
            all_day = False

            # Handle date vs dateTime
            if "date" in start:  # All-day event
                start_time = start["date"]
                all_day = True
            elif "dateTime" in start:
                start_time = start["dateTime"]

            if "date" in end:  # All-day event
                end_time = end["date"]
            elif "dateTime" in end:
                end_time = end["dateTime"]

            # Format attendees
            attendees = []
            for attendee in event.get("attendees", []):
                attendees.append(
                    {
                        "email": attendee.get("email"),
                        "display_name": attendee.get("displayName"),
                        "response_status": attendee.get("responseStatus"),
                        "optional": attendee.get("optional", False),
                        "organizer": attendee.get("organizer", False),
                    }
                )

            return {
                "id": event.get("id"),
                "title": event.get("summary"),
                "description": event.get("description"),
                "location": event.get("location"),
                "start_time": start_time,
                "end_time": end_time,
                "all_day": all_day,
                "status": event.get("status"),
                "created": event.get("created"),
                "updated": event.get("updated"),
                "creator": event.get("creator", {}),
                "organizer": event.get("organizer", {}),
                "attendees": attendees,
                "html_link": event.get("htmlLink"),
                "visibility": event.get("visibility", "default"),
                "recurring_event_id": event.get("recurringEventId"),
                "recurrence": event.get("recurrence", []),
            }
        except Exception as e:
            # Return basic event info if formatting fails
            return {
                "id": event.get("id"),
                "title": event.get("summary", "Unknown Event"),
                "error": f"Failed to format event: {str(e)}",
            }
