from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event


class DriveFileCreatedV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle file creation in drive.

        This event is triggered when a new file is created in a folder.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_drive_file_created_in_folder_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")

        # Build variables dictionary
        variables_dict = {
            "file_token": event_data.file_token if event_data.file_token else "",
            "file_type": event_data.file_type if event_data.file_type else "",
            "folder_token": event_data.folder_token if event_data.folder_token else "",
        }

        # Add operator information if available
        if event_data.operator_id:
            if event_data.operator_id.open_id:
                variables_dict["creator_open_id"] = event_data.operator_id.open_id
            if event_data.operator_id.user_id:
                variables_dict["creator_user_id"] = event_data.operator_id.user_id
            if event_data.operator_id.union_id:
                variables_dict["creator_union_id"] = event_data.operator_id.union_id

        return Variables(
            variables=variables_dict,
        )
