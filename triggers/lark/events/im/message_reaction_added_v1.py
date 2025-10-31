from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event


class MessageReactionAddedV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle the event when someone reacts to a message.
        
        This event is triggered when a user adds an emoji reaction to a message.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_im_message_reaction_created_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")
        
        # Build variables dictionary
        variables_dict = {
            "message_id": event_data.message_id if event_data.message_id else "",
            "operator_type": event_data.operator_type if event_data.operator_type else "",
            "action_time": event_data.action_time if event_data.action_time else "",
            "app_id": event_data.app_id if event_data.app_id else "",
        }
        
        # Add reaction emoji information
        if event_data.reaction_type:
            variables_dict["emoji_type"] = event_data.reaction_type.emoji_type if event_data.reaction_type.emoji_type else ""
        
        # Add user information
        if event_data.user_id:
            variables_dict["reactor_user_id"] = event_data.user_id.user_id if event_data.user_id.user_id else ""
            variables_dict["reactor_open_id"] = event_data.user_id.open_id if event_data.user_id.open_id else ""
            variables_dict["reactor_union_id"] = event_data.user_id.union_id if event_data.user_id.union_id else ""

        return Variables(
            variables=variables_dict,
        )