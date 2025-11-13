from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event, serialize_user_identity, serialize_user_list


class DriveFileTitleUpdatedV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle file title updated event.
        
        This event is triggered when a file's title is updated.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_drive_file_title_updated_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")
        
        # Build variables dictionary
        variables_dict: dict[str, Any] = {
            "file_token": event_data.file_token if event_data.file_token else "",
            "file_type": event_data.file_type if event_data.file_type else "",
        }
        
        # Add operator information
        operator = serialize_user_identity(event_data.operator_id)
        variables_dict.update({
            "operator_user_id": operator["user_id"],
            "operator_open_id": operator["open_id"],
            "operator_union_id": operator["union_id"],
        })
        
        # Add subscribers list
        subscribers = serialize_user_list(event_data.subscriber_id_list or [])
        variables_dict["subscribers"] = subscribers if subscribers else []

        return Variables(
            variables=variables_dict,
        )