from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event, serialize_user_id


class MessageReceiveV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle message receive event for group chats.

        This event is triggered when a message is sent to a group chat where the bot is a member.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_im_message_receive_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")

        # Build variables dictionary
        variables_dict: dict[str, Any] = {}

        # Add sender information
        if event_data.sender:
            if event_data.sender.sender_id:
                sender_id = serialize_user_id(event_data.sender.sender_id)
                variables_dict["sender_id"] = {
                    "user_id": sender_id["user_id"],
                    "open_id": sender_id["open_id"],
                    "union_id": sender_id["union_id"],
                }
            else:
                variables_dict["sender_id"] = {
                    "user_id": "",
                    "open_id": "",
                    "union_id": "",
                }

            variables_dict["sender_type"] = event_data.sender.sender_type if event_data.sender.sender_type else ""
            variables_dict["tenant_key"] = event_data.sender.tenant_key if event_data.sender.tenant_key else ""

        # Add message information
        if event_data.message:
            variables_dict["message_id"] = event_data.message.message_id if event_data.message.message_id else ""
            variables_dict["root_id"] = event_data.message.root_id if event_data.message.root_id else ""
            variables_dict["parent_id"] = event_data.message.parent_id if event_data.message.parent_id else ""
            variables_dict["chat_id"] = event_data.message.chat_id if event_data.message.chat_id else ""
            variables_dict["chat_type"] = event_data.message.chat_type if event_data.message.chat_type else ""
            variables_dict["message_type"] = event_data.message.message_type if event_data.message.message_type else ""
            variables_dict["content"] = event_data.message.content if event_data.message.content else ""
            variables_dict["create_time"] = event_data.message.create_time if event_data.message.create_time else ""
            variables_dict["update_time"] = event_data.message.update_time if event_data.message.update_time else ""

            # Add mentions if available
            if event_data.message.mentions:
                mentions_list = []
                for mention in event_data.message.mentions:
                    if mention:
                        mention_info = {
                            "key": mention.key if mention.key else "",
                            "id": serialize_user_id(mention.id) if mention.id else {},
                            "name": mention.name if mention.name else "",
                            "tenant_key": mention.tenant_key if mention.tenant_key else "",
                        }
                        mentions_list.append(mention_info)
                variables_dict["mentions"] = mentions_list
            else:
                variables_dict["mentions"] = []

        return Variables(
            variables=variables_dict,
        )
