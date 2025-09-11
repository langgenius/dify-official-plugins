import re
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolInvokeMessage


class SearchEventsTool(Tool):
    """
    Search for events across calendars with text query.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Search for events using text query.
        """
        # Check if credentials are available
        if "access_token" not in self.runtime.credentials:
            yield self.create_text_message(
                "Google Calendar access token is required. Please configure OAuth authentication."
            )
            return

        # Validate required parameters
        query = tool_parameters.get("query")
        if not query:
            yield self.create_text_message("Search query is required.")
            return

        # Extract parameters
        calendar_id = tool_parameters.get("calendar_id", "primary")
        time_min = tool_parameters.get("time_min")
        time_max = tool_parameters.get("time_max")
        max_results = tool_parameters.get("max_results", 25)
        order_by = tool_parameters.get("order_by", "startTime")
        show_deleted = tool_parameters.get("show_deleted", False)
        single_events = tool_parameters.get("single_events", True)

        access_token = self.runtime.credentials.get("access_token")

        # Start operation log
        operation_log = self.create_log_message(
            label="Search Events Operation",
            data={
                "calendar_id": calendar_id,
                "query": query,
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
                "q": query,
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

                # Filter events that match the query in case API search isn't precise
                relevant_events = self._filter_relevant_events(formatted_events, query)

                # Return structured data
                result = {
                    "success": True,
                    "message": f"Found {len(relevant_events)} events matching '{query}'",
                    "events": relevant_events,
                    "total_count": len(relevant_events),
                    "query": query,
                    "calendar_id": calendar_id,
                    "next_page_token": events_data.get("nextPageToken"),
                    "search_time_zone": events_data.get("timeZone"),
                }

                yield self.create_json_message(result)

                # Create user-friendly text summary
                if relevant_events:
                    summary_text = f"🔍 Found {len(relevant_events)} events matching '{query}':\n\n"

                    for i, event in enumerate(
                        relevant_events[:10], 1
                    ):  # Show first 10 results
                        summary_text += (
                            f"{i}. 📅 {event.get('title', 'Untitled Event')}\n"
                        )

                        # Add time information
                        start_time = event.get("start_time")
                        end_time = event.get("end_time")
                        if start_time and end_time:
                            summary_text += f"   🕒 {self._format_display_time(start_time)} - {self._format_display_time(end_time)}\n"
                        elif start_time:
                            summary_text += (
                                f"   🕒 {self._format_display_time(start_time)}\n"
                            )

                        # Add location if available
                        if event.get("location"):
                            summary_text += f"   📍 {event['location']}\n"

                        # Add description snippet if available
                        if event.get("description"):
                            desc = event["description"]
                            # Highlight query matches in description
                            if desc and query.lower() in desc.lower():
                                desc = self._highlight_text(desc, query)
                            desc = desc[:80] + "..." if len(desc) > 80 else desc
                            summary_text += f"   📝 {desc}\n"

                        summary_text += "\n"

                    if len(relevant_events) > 10:
                        summary_text += (
                            f"... and {len(relevant_events) - 10} more events\n"
                        )

                    yield self.create_text_message(summary_text)

                    # Provide search insights
                    insights = self._generate_search_insights(relevant_events, query)
                    if insights:
                        yield self.create_text_message(
                            f"💡 Search insights:\n{insights}"
                        )

                else:
                    yield self.create_text_message(
                        f"No events found matching '{query}' in the specified calendar and time range."
                    )

                    # Provide search suggestions
                    suggestions = self._generate_search_suggestions(query)
                    if suggestions:
                        yield self.create_text_message(
                            f"💡 Search suggestions:\n{suggestions}"
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
                    "Insufficient permissions to search this calendar."
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
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.isoformat()
                except ValueError:
                    continue

            return dt_string
        except Exception:
            return dt_string

    def _format_display_time(self, dt_string: str) -> str:
        """
        Format datetime for display purposes.
        """
        try:
            if "T" in dt_string:
                # It's a datetime
                dt = datetime.fromisoformat(dt_string.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d %H:%M")
            else:
                # It's a date
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
                "visibility": event.get("visibility", "default"),
                "recurring_event_id": event.get("recurringEventId"),
                "recurrence": event.get("recurrence", []),
            }
        except Exception:
            return {
                "id": event.get("id"),
                "title": event.get("summary", "Unknown Event"),
                "error": "Failed to format event",
            }

    def _filter_relevant_events(self, events: list, query: str) -> list:
        """
        Filter events to find the most relevant matches.
        """
        if not query:
            return events

        query_lower = query.lower()
        relevant_events = []

        for event in events:
            relevance_score = 0

            # Check title match
            title = event.get("title") or ""
            title_lower = title.lower()
            if query_lower in title_lower:
                relevance_score += 10
                if title_lower.startswith(query_lower):
                    relevance_score += 5

            # Check description match
            description = event.get("description") or ""
            description_lower = description.lower()
            if query_lower in description_lower:
                relevance_score += 5

            # Check location match
            location = event.get("location") or ""
            location_lower = location.lower()
            if query_lower in location_lower:
                relevance_score += 7

            # Check attendee names/emails
            for attendee in event.get("attendees", []):
                attendee_email = (attendee.get("email") or "").lower()
                attendee_name = (attendee.get("display_name") or "").lower()
                if query_lower in attendee_email or query_lower in attendee_name:
                    relevance_score += 3

            if relevance_score > 0:
                event["relevance_score"] = relevance_score
                relevant_events.append(event)

        # Sort by relevance score (descending)
        relevant_events.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

        return relevant_events

    def _highlight_text(self, text: str, query: str) -> str:
        """
        Highlight query matches in text.
        """
        try:
            # Simple highlighting with asterisks
            import re

            pattern = re.compile(re.escape(query), re.IGNORECASE)
            return pattern.sub(f"*{query}*", text)
        except Exception:
            return text

    def _generate_search_insights(self, events: list, query: str) -> str:
        """
        Generate insights about the search results.
        """
        if not events:
            return ""

        insights = []

        # Count by status
        statuses = {}
        for event in events:
            status = event.get("status", "confirmed")
            statuses[status] = statuses.get(status, 0) + 1

        if len(statuses) > 1:
            status_summary = ", ".join(
                [f"{count} {status}" for status, count in statuses.items()]
            )
            insights.append(f"Events by status: {status_summary}")

        # Count all-day vs timed events
        all_day_count = sum(1 for event in events if event.get("all_day", False))
        timed_count = len(events) - all_day_count

        if all_day_count > 0 and timed_count > 0:
            insights.append(
                f"{all_day_count} all-day events, {timed_count} timed events"
            )

        # Count events with attendees
        events_with_attendees = sum(1 for event in events if event.get("attendees"))
        if events_with_attendees > 0:
            insights.append(f"{events_with_attendees} events have attendees")

        return "\n".join(insights) if insights else ""

    def _generate_search_suggestions(self, query: str) -> str:
        """
        Generate search suggestions when no results are found.
        """
        suggestions = [
            "• Try using different keywords or phrases",
            "• Check if the event might be in a different calendar",
            "• Expand your time range with time_min and time_max parameters",
            "• Try searching for partial words (e.g., 'meet' instead of 'meeting')",
            "• Consider searching by location or attendee names",
        ]

        return "\n".join(suggestions)
