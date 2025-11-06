from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lark_oapi.api.contact.v3.model.department_event import DepartmentEvent
from lark_oapi.api.contact.v3.model.department_leader import DepartmentLeader
from lark_oapi.api.contact.v3.model.department_status import DepartmentStatus
from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from .._shared import dispatch_single_event, serialize_user_list


def _serialize_status(status: DepartmentStatus | None) -> dict[str, bool]:
    if status is None:
        return {"is_deleted": False}

    return {"is_deleted": bool(status.is_deleted) if status.is_deleted is not None else False}


def _serialize_leaders(leaders: list[DepartmentLeader] | None) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for leader in leaders or []:
        serialized.append(
            {
                "leader_type": leader.leader_type if leader.leader_type is not None else 0,
                "leader_id": getattr(leader, "leader_i_d", "") or "",
            }
        )
    return serialized


def _serialize_department(department: DepartmentEvent | None) -> dict[str, Any]:
    if department is None:
        return {}

    return {
        "department_id": department.department_id or "",
        "open_department_id": department.open_department_id or "",
        "name": department.name or "",
        "parent_department_id": department.parent_department_id or "",
        "leader_user_id": department.leader_user_id or "",
        "chat_id": department.chat_id or "",
        "order": department.order if department.order is not None else 0,
        "unit_ids": list(department.unit_ids or []),
        "status": _serialize_status(department.status),
        "leaders": _serialize_leaders(department.leaders),
        "department_hrbps": serialize_user_list(department.department_hrbps or []),
    }


class ContactDepartmentUpdatedV3Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """Handle contact department updated events."""

        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_contact_department_updated_v3,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")
        
        current_department = _serialize_department(event_data.object)
        previous_department = _serialize_department(event_data.old_object)
        status = current_department.get("status", {})

        variables_dict: dict[str, Any] = {
            "department_id": current_department.get("department_id", ""),
            "open_department_id": current_department.get("open_department_id", ""),
            "name": current_department.get("name", ""),
            "parent_department_id": current_department.get("parent_department_id", ""),
            "leader_user_id": current_department.get("leader_user_id", ""),
            "chat_id": current_department.get("chat_id", ""),
            "order": current_department.get("order", 0),
            "unit_ids": current_department.get("unit_ids", []),
            "is_deleted": status.get("is_deleted", False),
            "leaders": current_department.get("leaders", []),
            "department_hrbps": current_department.get("department_hrbps", []),
            "current_department_json": current_department,
            "previous_department_json": previous_department,
        }

        return Variables(
            variables=variables_dict,
        )
