from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event


class ChatMemberUserWithdrawnV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle the event when a user withdraws from a chat group.

        This event is triggered when a user voluntarily withdraws/leaves from a chat group.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_im_chat_member_user_withdrawn_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")

        # Build variables dictionary
        variables_dict: dict[str, Any] = {
            "chat_id": event_data.chat_id if event_data.chat_id else "",
            "name": event_data.name if event_data.name else "",
            "operator_tenant_key": event_data.operator_tenant_key if event_data.operator_tenant_key else "",
        }

        # Add withdrawn user information
        if event_data.users:
            withdrawn_users = []
            for user in event_data.users:
                if user:
                    user_info = {
                        "name": user.name if user.name else "",
                        "tenant_key": user.tenant_key if user.tenant_key else "",
                    }
                    if user.user_id:
                        user_info["user_id"] = user.user_id.user_id if user.user_id.user_id else ""
                        user_info["open_id"] = user.user_id.open_id if user.user_id.open_id else ""
                        user_info["union_id"] = user.user_id.union_id if user.user_id.union_id else ""
                    withdrawn_users.append(user_info)

            variables_dict["withdrawn_users"] = withdrawn_users
            variables_dict["withdrawn_users_count"] = len(withdrawn_users)
        else:
            variables_dict["withdrawn_users"] = []
            variables_dict["withdrawn_users_count"] = 0

        return Variables(
            variables=variables_dict,
        )
