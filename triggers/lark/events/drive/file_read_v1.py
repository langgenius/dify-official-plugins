from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event, serialize_user_list


class DriveFileReadV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle file read event.
        
        This event is triggered when a file is read/viewed.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_drive_file_read_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")
        
        # Build variables dictionary
        variables_dict: dict[str, Any] = {
            "file_token": event_data.file_token if event_data.file_token else "",
            "file_type": event_data.file_type if event_data.file_type else "",
        }
        
        # Add operator information (list of users who read the file)
        operators = serialize_user_list(event_data.operator_id_list or [])
        if operators and len(operators) > 0:
            # Use the first operator as the main operator
            variables_dict.update({
                "operator_user_id": operators[0]["user_id"],
                "operator_open_id": operators[0]["open_id"],
                "operator_union_id": operators[0]["union_id"],
            })
        else:
            variables_dict.update({
                "operator_user_id": "",
                "operator_open_id": "",
                "operator_union_id": "",
            })
        
        # Also provide the full list of operators
        variables_dict["operators"] = operators

        return Variables(
            variables=variables_dict,
        )