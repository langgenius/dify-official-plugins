from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from .._shared import dispatch_single_event


class ContactUserDeletedV3Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle employee deletion/departure event.

        This event is triggered when an employee is deleted from the organization or leaves.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_contact_user_deleted_v3,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")

        # Build variables dictionary with basic user information
        variables_dict = {}

        # Extract current (deleted) user information
        if event_data.object:
            user_data = event_data.object
            variables_dict.update(
                {
                    "user_id": user_data.user_id if user_data.user_id else "",
                    "open_id": user_data.open_id if user_data.open_id else "",
                    "union_id": user_data.union_id if user_data.union_id else "",
                    "name": user_data.name if user_data.name else "",
                    "en_name": user_data.en_name if user_data.en_name else "",
                    "email": user_data.email if user_data.email else "",
                    "mobile": user_data.mobile if user_data.mobile else "",
                    "employee_no": user_data.employee_no if user_data.employee_no else "",
                    "employee_type": str(user_data.employee_type) if user_data.employee_type is not None else "0",
                }
            )

            # Add department IDs
            if user_data.department_ids:
                variables_dict["department_ids"] = list(user_data.department_ids)
            else:
                variables_dict["department_ids"] = []

        # Extract previous user information (before deletion)
        if event_data.old_object:
            old_data = event_data.old_object
            old_user_info = {
                "open_id": old_data.open_id if old_data.open_id else "",
                "department_ids": list(old_data.department_ids) if old_data.department_ids else [],
            }
            variables_dict["old_user_info"] = old_user_info
        else:
            variables_dict["old_user_info"] = {}

        return Variables(
            variables=variables_dict,
        )
