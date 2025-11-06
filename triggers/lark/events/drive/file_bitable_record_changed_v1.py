from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event, serialize_user_identity, serialize_user_list


class DriveFileBitableRecordChangedV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle bitable record changed event.
        
        This event is triggered when a record in a bitable (database table) is changed.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_drive_file_bitable_record_changed_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")
        
        # Build variables dictionary
        variables_dict: dict[str, Any] = {
            "file_token": event_data.file_token if event_data.file_token else "",
            "file_type": event_data.file_type if event_data.file_type else "",
            "table_id": event_data.table_id if event_data.table_id else "",
            "revision": event_data.revision if event_data.revision else 0,
            "update_time": event_data.update_time if event_data.update_time else "",
        }
        
        # Add operator information
        operator = serialize_user_identity(event_data.operator_id)
        variables_dict.update({
            "operator_user_id": operator["user_id"],
            "operator_open_id": operator["open_id"],
            "operator_union_id": operator["union_id"],
        })
        
        # Add subscribers
        subscribers = serialize_user_list(event_data.subscriber_id_list or [])
        variables_dict["subscribers"] = subscribers
        
        # Process action list
        if event_data.action_list:
            actions = []
            for action in event_data.action_list:
                if action:
                    action_info = {
                        "action": action.action if action.action else "",
                        "record_id": action.record_id if action.record_id else "",
                        "before_value": action.before_value if action.before_value else "",
                        "after_value": action.after_value if action.after_value else "",
                    }
                    actions.append(action_info)
            variables_dict["actions"] = actions
            variables_dict["action_count"] = len(actions)
        else:
            variables_dict["actions"] = []
            variables_dict["action_count"] = 0

        return Variables(
            variables=variables_dict,
        )