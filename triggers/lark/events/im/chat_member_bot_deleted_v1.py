from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event


class ChatMemberBotDeletedV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle the event when a bot is removed from a chat group.

        This event is triggered when a bot is removed from a group chat.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_im_chat_member_bot_deleted_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")

        # Build variables dictionary
        variables_dict: dict[str, Any] = {
            "chat_id": event_data.chat_id if event_data.chat_id else "",
            "name": event_data.name if event_data.name else "",
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
        else:
            variables_dict["operator_user_id"] = ""
            variables_dict["operator_open_id"] = ""
            variables_dict["operator_union_id"] = ""

        # Add i18n names if available
        if event_data.i18n_names:
            variables_dict["i18n_names"] = {
                "zh_cn": event_data.i18n_names.zh_cn if event_data.i18n_names.zh_cn else "",
                "en_us": event_data.i18n_names.en_us if event_data.i18n_names.en_us else "",
                "ja_jp": event_data.i18n_names.ja_jp if event_data.i18n_names.ja_jp else "",
            }
        else:
            variables_dict["i18n_names"] = {}

        return Variables(
            variables=variables_dict,
        )