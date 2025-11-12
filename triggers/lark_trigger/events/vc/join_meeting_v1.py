from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event


class VcJoinMeetingV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle video conference join meeting event.
        
        This event is triggered when a user joins a video conference meeting.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_vc_meeting_join_meeting_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")
        
        # Build variables dictionary
        variables_dict: dict[str, Any] = {}
        
        # Add meeting information
        if event_data.meeting:
            variables_dict.update({
                "meeting_id": event_data.meeting.id if event_data.meeting.id else "",
                "meeting_no": event_data.meeting.meeting_no if event_data.meeting.meeting_no else "",
                "topic": event_data.meeting.topic if event_data.meeting.topic else "",
                "start_time": str(event_data.meeting.start_time) if event_data.meeting.start_time else "",
                "meeting_source": event_data.meeting.meeting_source if event_data.meeting.meeting_source else "",
                "calendar_event_id": event_data.meeting.calendar_event_id if event_data.meeting.calendar_event_id else "",
            })
            
            # Add host information
            if event_data.meeting.host_user:
                variables_dict.update({
                    "host_user_id": event_data.meeting.host_user.id if event_data.meeting.host_user.id else "",
                    "host_user_type": str(event_data.meeting.host_user.user_type) if event_data.meeting.host_user.user_type else "",
                })
        
        # Add operator information
        if event_data.operator:
            variables_dict.update({
                "operator_id": event_data.operator.id if event_data.operator.id else "",
                "operator_user_type": str(event_data.operator.user_type) if event_data.operator.user_type else "",
            })

        return Variables(
            variables=variables_dict,
        )