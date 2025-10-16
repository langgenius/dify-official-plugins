from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event


class MessageReadV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle the event when messages are marked as read.

        This event is triggered when a user reads one or more messages.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_im_message_message_read_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")

        # Build variables dictionary
        variables_dict = {}

        # Add reader information
        if event_data.reader:
            variables_dict["reader_id"] = event_data.reader.reader_id if event_data.reader.reader_id else ""
            variables_dict["read_time"] = event_data.reader.read_time if event_data.reader.read_time else ""
            variables_dict["tenant_key"] = event_data.reader.tenant_key if event_data.reader.tenant_key else ""

        # Add message IDs that were read
        if event_data.message_id_list:
            variables_dict["message_ids_read"] = list(event_data.message_id_list)
            variables_dict["message_count"] = len(event_data.message_id_list)
        else:
            variables_dict["message_ids_read"] = []
            variables_dict["message_count"] = 0

        return Variables(
            variables=variables_dict,
        )
