from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event, serialize_user_identity, serialize_user_list


class DriveFileTrashedV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        """
        Handle file moved to trash event.
        
        This event is triggered when a file is moved to the trash/recycle bin.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_drive_file_trashed_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")
        
        # Build variables dictionary
        operator = serialize_user_identity(event_data.operator_id)
        subscribers = serialize_user_list(event_data.subscriber_id_list or [])
        
        variables_dict = {
            "file_token": event_data.file_token if event_data.file_token else "",
            "file_type": event_data.file_type if event_data.file_type else "",
            "operator_user_id": operator["user_id"],
            "operator_open_id": operator["open_id"],
            "operator_union_id": operator["union_id"],
        }
        
        # Add subscribers list
        variables_dict["subscribers"] = subscribers if subscribers else []

        return Variables(
            variables=variables_dict,
        )