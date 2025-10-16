from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event, serialize_user_list


class CalendarChangedV4Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle calendar changed event.

        This event is triggered when a calendar's properties are modified.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_calendar_calendar_changed_v4,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")

        # Build variables dictionary with affected users
        affected_users = serialize_user_list(event_data.user_id_list or [])
        
        variables_dict: dict[str, Any] = {
            "affected_users": affected_users,
            "affected_users_count": len(affected_users),
        }

        return Variables(
            variables=variables_dict,
        )