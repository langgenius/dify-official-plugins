import json
import re
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class CreateEventTool(Tool):
    """
    Create a new event in a Google Calendar.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a new calendar event.
        """
        # Check if credentials are available
        if "access_token" not in self.runtime.credentials:
            yield self.create_text_message(
                "Google Calendar access token is required. Please configure OAuth authentication."
            )
            return

        # Validate required parameters
        title = tool_parameters.get("title")
        if not title:
            yield self.create_text_message("Event title is required.")
            return

        start_time = tool_parameters.get("start_time")
        if not start_time:
            yield self.create_text_message("Event start time is required.")
            return

        # Extract parameters
        calendar_id = tool_parameters.get("calendar_id", "primary")
        end_time = tool_parameters.get("end_time")
        all_day = tool_parameters.get("all_day", False)
        description = tool_parameters.get("description")
        location = tool_parameters.get("location")
        attendees = tool_parameters.get("attendees", [])
        time_zone = tool_parameters.get("time_zone")
        visibility = tool_parameters.get("visibility", "default")
        send_notifications = tool_parameters.get("send_notifications", True)

        access_token = self.runtime.credentials.get("access_token")

        # Start operation log
        operation_log = self.create_log_message(
            label="Create Event Operation",
            data={
                "calendar_id": calendar_id,
                "title": title,
                "start_time": start_time,
                "end_time": end_time,
                "all_day": all_day,
            },
            status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
        )
        yield operation_log

        try:
            # Build event data
            event_data = self._build_event_data(
                title=title,
                start_time=start_time,
                end_time=end_time,
                all_day=all_day,
                description=description,
                location=location,
                attendees=attendees,
                time_zone=time_zone,
                visibility=visibility,
            )

            if not event_data:
                yield self.create_text_message(
                    "Failed to build event data. Please check the input parameters."
                )
                return

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            # Build query parameters
            params = {}
            if send_notifications:
                params["sendNotifications"] = "true"

            # Make API call
            api_url = (
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
            )

            api_log = self.create_log_message(
                label="API Call",
                data={"endpoint": api_url, "event_data": event_data},
                status=InvokeMessage.LogMessage.LogStatus.SUCCESS,
                parent=operation_log,
            )
            yield api_log

            response = requests.post(
                api_url,
                headers=headers,
                params=params,
                data=json.dumps(event_data),
                timeout=30,
            )

            if response.status_code in [200, 201]:
                created_event = response.json()

                # Format the response
                result = {
                    "success": True,
                    "message": f"Event '{title}' created successfully",
                    "event": self._format_event(created_event),
                    "event_id": created_event.get("id"),
                    "html_link": created_event.get("htmlLink"),
                    "ical_uid": created_event.get("iCalUID"),
                }

                yield self.create_json_message(result)

                # Create user-friendly text response
                success_text = f"✅ Event created successfully!\n\n"
                success_text += f"📅 Title: {title}\n"

                if start_time:
                    success_text += f"🕒 Start: {start_time}\n"
                if end_time:
                    success_text += f"🕒 End: {end_time}\n"
                if all_day:
                    success_text += f"📆 All-day event\n"
                if location:
                    success_text += f"📍 Location: {location}\n"
                if description:
                    desc = (
                        description[:100] + "..."
                        if len(description) > 100
                        else description
                    )
                    success_text += f"📝 Description: {desc}\n"
                if attendees:
                    success_text += f"👥 Attendees: {len(attendees)} invited\n"

                success_text += f"\n🔗 View in Google Calendar: {created_event.get('htmlLink', 'N/A')}\n"
                success_text += f"🆔 Event ID: {created_event.get('id', 'N/A')}"

                yield self.create_text_message(success_text)

                # Create a link to the event
                if created_event.get("htmlLink"):
                    yield self.create_link_message(created_event["htmlLink"])

            elif response.status_code == 400:
                error_data = response.json()
                error_message = error_data.get("error", {}).get(
                    "message", "Invalid request"
                )
                yield self.create_log_message(
                    label="Bad Request Error",
                    data={"status_code": response.status_code, "error": error_message},
                    status=InvokeMessage.LogMessage.LogStatus.ERROR,
                )
                yield self.create_text_message(f"Invalid request: {error_message}")

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
                    "Insufficient permissions to create events in this calendar."
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

        except json.JSONDecodeError as e:
            yield self.create_log_message(
                label="JSON Error",
                data={"error": str(e)},
                status=InvokeMessage.LogMessage.LogStatus.ERROR,
            )
            yield self.create_text_message(f"Failed to encode event data: {str(e)}")
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

    def _build_event_data(
        self,
        title: str,
        start_time: str,
        end_time: str = None,
        all_day: bool = False,
        description: str = None,
        location: str = None,
        attendees: list = None,
        time_zone: str = None,
        visibility: str = "default",
    ) -> dict:
        """
        Build the event data dictionary for the API request.
        """
        try:
            event_data = {"summary": title, "visibility": visibility}

            # Add description if provided
            if description:
                event_data["description"] = description

            # Add location if provided
            if location:
                event_data["location"] = location

            # Handle date/time
            if all_day:
                # All-day events use date format
                start_date = self._extract_date_from_datetime(start_time)
                event_data["start"] = {"date": start_date}

                if end_time:
                    end_date = self._extract_date_from_datetime(end_time)
                    event_data["end"] = {"date": end_date}
                else:
                    # If no end date, use same as start date
                    event_data["end"] = {"date": start_date}
            else:
                # Regular events use dateTime format
                formatted_start = self._format_datetime(start_time)
                event_data["start"] = {"dateTime": formatted_start}

                if time_zone:
                    event_data["start"]["timeZone"] = time_zone

                if end_time:
                    formatted_end = self._format_datetime(end_time)
                    event_data["end"] = {"dateTime": formatted_end}
                    if time_zone:
                        event_data["end"]["timeZone"] = time_zone
                else:
                    # If no end time specified, make it 1 hour duration
                    try:
                        start_dt = datetime.fromisoformat(
                            formatted_start.replace("Z", "+00:00")
                        )
                        end_dt = (
                            start_dt.replace(hour=start_dt.hour + 1)
                            if start_dt.hour < 23
                            else start_dt.replace(hour=23, minute=59)
                        )
                        formatted_end = end_dt.isoformat()
                        event_data["end"] = {"dateTime": formatted_end}
                        if time_zone:
                            event_data["end"]["timeZone"] = time_zone
                    except Exception:
                        # Fallback: use start time as end time
                        event_data["end"] = {"dateTime": formatted_start}
                        if time_zone:
                            event_data["end"]["timeZone"] = time_zone

            # Add attendees if provided
            if attendees:
                attendee_list = []
                for attendee in attendees:
                    if isinstance(attendee, str):
                        # Simple email string
                        attendee_list.append({"email": attendee})
                    elif isinstance(attendee, dict):
                        # Attendee object with more details
                        attendee_obj = {"email": attendee.get("email")}
                        if attendee.get("displayName"):
                            attendee_obj["displayName"] = attendee["displayName"]
                        if attendee.get("optional"):
                            attendee_obj["optional"] = attendee["optional"]
                        attendee_list.append(attendee_obj)

                if attendee_list:
                    event_data["attendees"] = attendee_list

            return event_data

        except Exception as e:
            print(f"Error building event data: {str(e)}")
            return None

    def _format_datetime(self, dt_string: str) -> str:
        """
        Format datetime string to RFC3339 format expected by Google Calendar API.
        """
        try:
            # If it's already in RFC3339 format, return as is
            if re.match(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2}|Z)",
                dt_string,
            ):
                return dt_string

            # Try parsing common formats
            for fmt in [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M",
            ]:
                try:
                    dt = datetime.strptime(dt_string, fmt)
                    # Add timezone if not present
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.isoformat()
                except ValueError:
                    continue

            # If no format matches, assume it's a date and add default time
            try:
                dt = datetime.strptime(dt_string, "%Y-%m-%d")
                dt = dt.replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except ValueError:
                pass

            # Last resort: return as is
            return dt_string

        except Exception:
            return dt_string

    def _extract_date_from_datetime(self, dt_string: str) -> str:
        """
        Extract date part from datetime string for all-day events.
        """
        try:
            # Try to parse and extract date
            for fmt in [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M",
                "%Y-%m-%d",
            ]:
                try:
                    dt = datetime.strptime(dt_string, fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue

            # If already in date format
            if re.match(r"^\d{4}-\d{2}-\d{2}$", dt_string):
                return dt_string

            # Extract date from ISO format
            if "T" in dt_string:
                return dt_string.split("T")[0]

            # Return as is if can't parse
            return dt_string
        except Exception:
            return dt_string

    def _format_event(self, event: dict) -> dict:
        """
        Format event data for consistent output.
        """
        try:
            # Extract start and end times
            start = event.get("start", {})
            end = event.get("end", {})

            start_time = start.get("dateTime") or start.get("date")
            end_time = end.get("dateTime") or end.get("date")
            all_day = "date" in start

            # Format attendees
            attendees = []
            for attendee in event.get("attendees", []):
                attendees.append(
                    {
                        "email": attendee.get("email"),
                        "display_name": attendee.get("displayName"),
                        "response_status": attendee.get("responseStatus"),
                        "optional": attendee.get("optional", False),
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
                "ical_uid": event.get("iCalUID"),
                "visibility": event.get("visibility", "default"),
            }
        except Exception as e:
            return {
                "id": event.get("id"),
                "title": event.get("summary", "Unknown Event"),
                "error": f"Failed to format event: {str(e)}",
            }
