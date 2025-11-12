from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event


class ChatUpdatedV1Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle the event when chat information is updated.

        This event is triggered when a chat group's information is modified, such as name, description, or settings.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_im_chat_updated_v1,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")

        # Build variables dictionary
        variables_dict: dict[str, Any] = {
            "chat_id": event_data.chat_id if event_data.chat_id else "",
            "external": str(event_data.external) if event_data.external is not None else "false",
            "operator_tenant_key": event_data.operator_tenant_key if event_data.operator_tenant_key else "",
        }

        # Add operator information if available
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

        # Add before and after change information
        if event_data.before_change:
            before_dict = {}
            if hasattr(event_data.before_change, "name"):
                before_dict["name"] = event_data.before_change.name or ""
            if hasattr(event_data.before_change, "description"):
                before_dict["description"] = event_data.before_change.description or ""
            if hasattr(event_data.before_change, "owner_id"):
                before_dict["owner_id"] = event_data.before_change.owner_id or ""
            variables_dict["before_change"] = before_dict
        else:
            variables_dict["before_change"] = {}

        if event_data.after_change:
            after_dict = {}
            if hasattr(event_data.after_change, "name"):
                after_dict["name"] = event_data.after_change.name or ""
            if hasattr(event_data.after_change, "description"):
                after_dict["description"] = event_data.after_change.description or ""
            if hasattr(event_data.after_change, "owner_id"):
                after_dict["owner_id"] = event_data.after_change.owner_id or ""
            variables_dict["after_change"] = after_dict
        else:
            variables_dict["after_change"] = {}

        # Add moderator list changes
        if event_data.moderator_list:
            moderator_changes = {}
            if event_data.moderator_list.added_member_list:
                added = []
                for mod in event_data.moderator_list.added_member_list:
                    if mod:
                        added.append(
                            {
                                "user_id": mod.user_id if hasattr(mod, "user_id") and mod.user_id else "",
                                "tenant_key": mod.tenant_key if hasattr(mod, "tenant_key") and mod.tenant_key else "",
                            }
                        )
                moderator_changes["added"] = added
            else:
                moderator_changes["added"] = []

            if event_data.moderator_list.removed_member_list:
                removed = []
                for mod in event_data.moderator_list.removed_member_list:
                    if mod:
                        removed.append(
                            {
                                "user_id": mod.user_id if hasattr(mod, "user_id") and mod.user_id else "",
                                "tenant_key": mod.tenant_key if hasattr(mod, "tenant_key") and mod.tenant_key else "",
                            }
                        )
                moderator_changes["removed"] = removed
            else:
                moderator_changes["removed"] = []

            variables_dict["moderator_changes"] = moderator_changes
        else:
            variables_dict["moderator_changes"] = {"added": [], "removed": []}

        return Variables(
            variables=variables_dict,
        )
