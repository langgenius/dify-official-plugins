from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event


class MeetingRoomCreatedV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle meeting room created event.
        
        This event is triggered when a new meeting room is created.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_meeting_room_meeting_room_created_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")
        
        # Build variables dictionary
        variables_dict: dict[str, Any] = {
            "room_id": event_data.room_id if event_data.room_id else "",
            "room_name": event_data.room_name if event_data.room_name else "",
        }

        return Variables(
            variables=variables_dict,
        )