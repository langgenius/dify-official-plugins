from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event


class MessageReactionDeletedV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle message reaction deletion event.

        This event is triggered when a reaction is removed from a message.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_im_message_reaction_deleted_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")

        # Build variables dictionary
        variables_dict: dict[str, Any] = {
            "message_id": event_data.message_id if event_data.message_id else "",
            "reaction_type": event_data.reaction_type if event_data.reaction_type else "",
        }

        # Add operator information
        if event_data.operator_type:
            variables_dict["operator_type"] = event_data.operator_type
        else:
            variables_dict["operator_type"] = ""

        # Add user ID based on operator type
        if event_data.user_id:
            variables_dict["user_open_id"] = event_data.user_id.open_id if event_data.user_id.open_id else ""
            variables_dict["user_user_id"] = event_data.user_id.user_id if event_data.user_id.user_id else ""
            variables_dict["user_union_id"] = event_data.user_id.union_id if event_data.user_id.union_id else ""
        else:
            variables_dict["user_open_id"] = ""
            variables_dict["user_user_id"] = ""
            variables_dict["user_union_id"] = ""

        # Add app ID if operator is an app
        if event_data.app_id:
            variables_dict["app_id"] = event_data.app_id
        else:
            variables_dict["app_id"] = ""

        # Add action time
        if event_data.action_time:
            variables_dict["action_time"] = event_data.action_time
        else:
            variables_dict["action_time"] = ""

        return Variables(
            variables=variables_dict,
        )