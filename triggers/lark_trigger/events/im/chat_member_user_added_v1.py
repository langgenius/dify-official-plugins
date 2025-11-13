from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event


class ChatMemberUserAddedV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle the event when new members join a chat group.

        This event is triggered when one or more users are added to a chat group.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_im_chat_member_user_added_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")

        # Build variables dictionary
        variables_dict: dict[str, Any] = {
            "chat_id": event_data.chat_id if event_data.chat_id else "",
            "chat_name": event_data.name if event_data.name else "",
            "is_external": str(event_data.external) if event_data.external is not None else "false",
            "operator_tenant_key": event_data.operator_tenant_key if event_data.operator_tenant_key else "",
        }

        # Add operator information
        if event_data.operator_id:
            variables_dict["operator_user_id"] = (
                event_data.operator_id.user_id if event_data.operator_id.user_id else ""
            )
            variables_dict["operator_open_id"] = (
                event_data.operator_id.open_id if event_data.operator_id.open_id else ""
            )
            variables_dict["operator_union_id"] = (
                event_data.operator_id.union_id if event_data.operator_id.union_id else ""
            )

        # Add new members information
        if event_data.users:
            members_list = []
            for idx, user in enumerate(event_data.users):
                if user:
                    member_info = {
                        "name": user.name if user.name else "",
                        "tenant_key": user.tenant_key if user.tenant_key else "",
                    }
                    if user.user_id:
                        member_info["user_id"] = user.user_id.user_id if user.user_id.user_id else ""
                        member_info["open_id"] = user.user_id.open_id if user.user_id.open_id else ""
                        member_info["union_id"] = user.user_id.union_id if user.user_id.union_id else ""
                    members_list.append(member_info)

            # Store list directly
            variables_dict["new_members"] = members_list
            variables_dict["new_members_count"] = len(members_list)
        else:
            variables_dict["new_members"] = []
            variables_dict["new_members_count"] = 0

        return Variables(
            variables=variables_dict,
        )
