from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event


class VcRecordingReadyV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle video conference recording ready event.
        
        This event is triggered when a meeting recording is ready for download.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_vc_meeting_recording_ready_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")
        
        # Build variables dictionary
        variables_dict: dict[str, Any] = {
            "recording_url": event_data.url if event_data.url else "",
            "duration": event_data.duration if event_data.duration else 0,
        }
        
        # Add meeting information
        if event_data.meeting:
            variables_dict.update({
                "meeting_id": event_data.meeting.id if event_data.meeting.id else "",
                "meeting_no": event_data.meeting.meeting_no if event_data.meeting.meeting_no else "",
                "topic": event_data.meeting.topic if event_data.meeting.topic else "",
                "start_time": str(event_data.meeting.start_time) if event_data.meeting.start_time else "",
                "end_time": str(event_data.meeting.end_time) if event_data.meeting.end_time else "",
            })
            
            # Add host information
            if event_data.meeting.host_user:
                variables_dict.update({
                    "host_user_id": event_data.meeting.host_user.id if event_data.meeting.host_user.id else "",
                    "host_user_type": str(event_data.meeting.host_user.user_type) if event_data.meeting.host_user.user_type else "",
                })

        return Variables(
            variables=variables_dict,
        )