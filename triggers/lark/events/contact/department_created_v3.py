from typing import Any, Mapping
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from examples.lark_trigger.events._shared import dispatch_single_event


class ContactDepartmentCreatedV3Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Handle new department creation event.

        This event is triggered when a new department is created in the organization.
        """
        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_contact_department_created_v3,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")

        dept_data = event_data.object
        if dept_data is None:
            raise ValueError("dept_data is None")

        # Build variables dictionary with explicit fields
        variables_dict = {
            # Department IDs
            "department_id": dept_data.department_id if dept_data.department_id else "",
            "open_department_id": dept_data.open_department_id if dept_data.open_department_id else "",
            "parent_department_id": dept_data.parent_department_id if dept_data.parent_department_id else "",
            # Basic information
            "name": dept_data.name if dept_data.name else "",
            "chat_id": dept_data.chat_id if dept_data.chat_id else "",
            # Leadership
            "leader_user_id": dept_data.leader_user_id if dept_data.leader_user_id else "",
            # Order and status
            "order": dept_data.order if dept_data.order is not None else 0,
            "status": dept_data.status if dept_data.status else "",
        }

        # Add unit IDs as array
        if dept_data.unit_ids:
            variables_dict["unit_ids"] = dept_data.unit_ids
        else:
            variables_dict["unit_ids"] = []

        # Add leaders list as array
        if dept_data.leaders:
            leaders_list = []
            for leader in dept_data.leaders:
                if leader:
                    leader_info = {
                        "leader_type": leader.leader_type if leader.leader_type else 0,
                        "leader_id": leader.leader_i_d if leader.leader_i_d else "",
                    }
                    leaders_list.append(leader_info)
            variables_dict["leaders"] = leaders_list
        else:
            variables_dict["leaders"] = []

        # Add HRBPs list as array
        if dept_data.department_hrbps:
            variables_dict["hrbps"] = dept_data.department_hrbps
        else:
            variables_dict["hrbps"] = []

        return Variables(
            variables=variables_dict,
        )
