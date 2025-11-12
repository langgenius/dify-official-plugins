from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event


class MessageRecalledV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle the event when a message is recalled/withdrawn.
        
        This event is triggered when a user recalls (withdraws) a message they previously sent.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_im_message_recalled_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")
        
        # Build variables dictionary
        variables_dict = {
            "message_id": event_data.message_id if event_data.message_id else "",
            "chat_id": event_data.chat_id if event_data.chat_id else "",
            "recall_time": event_data.recall_time if event_data.recall_time else "",
            "recall_type": event_data.recall_type if event_data.recall_type else "",
        }

        return Variables(
            variables=variables_dict,
        )