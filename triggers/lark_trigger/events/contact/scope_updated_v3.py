from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event, serialize_user_list


class ContactScopeUpdatedV3Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle contact scope updated event.

        This event is triggered when contact visibility scope is updated.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_contact_scope_updated_v3,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")

        # Build variables dictionary
        variables_dict: dict[str, Any] = {}

        # Process added scope
        if event_data.added:
            added_scope = {
                "users": serialize_user_list(event_data.added.users or []),
                "departments": list(event_data.added.departments) if event_data.added.departments else [],
                "user_groups": list(event_data.added.user_groups) if event_data.added.user_groups else [],
            }
            variables_dict["added_scope"] = added_scope
        else:
            variables_dict["added_scope"] = {
                "users": [],
                "departments": [],
                "user_groups": [],
            }

        # Process removed scope
        if event_data.removed:
            removed_scope = {
                "users": serialize_user_list(event_data.removed.users or []),
                "departments": list(event_data.removed.departments) if event_data.removed.departments else [],
                "user_groups": list(event_data.removed.user_groups) if event_data.removed.user_groups else [],
            }
            variables_dict["removed_scope"] = removed_scope
        else:
            variables_dict["removed_scope"] = {
                "users": [],
                "departments": [],
                "user_groups": [],
            }

        return Variables(
            variables=variables_dict,
        )