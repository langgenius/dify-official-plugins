from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lark_oapi.api.contact.v3.model.custom_attr_generic_user import CustomAttrGenericUser
from lark_oapi.api.contact.v3.model.user_custom_attr import UserCustomAttr
from lark_oapi.api.contact.v3.model.user_custom_attr_value import UserCustomAttrValue
from lark_oapi.api.contact.v3.model.user_event import UserEvent
from lark_oapi.api.contact.v3.model.user_order import UserOrder
from lark_oapi.api.contact.v3.model.user_position import UserPosition
from lark_oapi.api.contact.v3.model.user_status import UserStatus
from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from .._shared import dispatch_single_event


def _serialize_status(status: UserStatus | None) -> dict[str, bool]:
    if status is None:
        return {
            "is_frozen": False,
            "is_resigned": False,
            "is_activated": False,
            "is_exited": False,
            "is_unjoin": False,
        }

    return {
        "is_frozen": bool(status.is_frozen),
        "is_resigned": bool(status.is_resigned),
        "is_activated": bool(status.is_activated),
        "is_exited": bool(status.is_exited),
        "is_unjoin": bool(status.is_unjoin),
    }


def _serialize_positions(positions: list[UserPosition] | None) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for position in positions or []:
        serialized.append(
            {
                "position_code": position.position_code or "",
                "position_name": position.position_name or "",
                "department_id": position.department_id or "",
                "leader_user_id": position.leader_user_id or "",
                "leader_position_code": position.leader_position_code or "",
                "is_major": bool(position.is_major),
            }
        )
    return serialized


def _serialize_orders(orders: list[UserOrder] | None) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for order in orders or []:
        serialized.append(
            {
                "department_id": order.department_id or "",
                "user_order": order.user_order if order.user_order is not None else 0,
                "department_order": order.department_order if order.department_order is not None else 0,
                "is_primary_dept": bool(order.is_primary_dept),
            }
        )
    return serialized


def _serialize_custom_attr_value(value: UserCustomAttrValue | None) -> dict[str, Any]:
    if value is None:
        return {}

    generic_user: CustomAttrGenericUser | None = value.generic_user
    generic_user_dict: dict[str, Any] = {}
    if generic_user is not None:
        generic_user_dict = {
            "id": generic_user.id or "",
            "type": generic_user.type if generic_user.type is not None else 0,
        }

    return {
        "text": value.text or "",
        "url": value.url or "",
        "pc_url": value.pc_url or "",
        "option_id": value.option_id or "",
        "option_value": value.option_value or "",
        "name": value.name or "",
        "picture_url": value.picture_url or "",
        "generic_user": generic_user_dict,
    }


def _serialize_custom_attrs(custom_attrs: list[UserCustomAttr] | None) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for attr in custom_attrs or []:
        serialized.append(
            {
                "type": attr.type or "",
                "id": attr.id or "",
                "value": _serialize_custom_attr_value(attr.value),
            }
        )
    return serialized


def _build_user_snapshot(user: UserEvent | None) -> dict[str, Any]:
    if user is None:
        return {}

    status = _serialize_status(user.status)
    positions = _serialize_positions(user.positions)
    orders = _serialize_orders(user.orders)
    custom_attrs = _serialize_custom_attrs(user.custom_attrs)

    return {
        "user_id": user.user_id or "",
        "open_id": user.open_id or "",
        "union_id": user.union_id or "",
        "name": user.name or "",
        "en_name": user.en_name or "",
        "nickname": user.nickname or "",
        "email": user.email or "",
        "enterprise_email": user.enterprise_email or "",
        "job_title": user.job_title or "",
        "mobile": user.mobile or "",
        "mobile_visible": bool(user.mobile_visible),
        "gender": user.gender if user.gender is not None else 0,
        "avatar_key": user.avatar.avatar_72 if user.avatar and user.avatar.avatar_72 else "",
        "status": status,
        "department_ids": list(user.department_ids or []),
        "leader_user_id": user.leader_user_id or "",
        "city": user.city or "",
        "country": user.country or "",
        "work_station": user.work_station or "",
        "join_time": user.join_time if user.join_time is not None else 0,
        "is_tenant_manager": bool(user.is_tenant_manager),
        "employee_no": user.employee_no or "",
        "employee_type": user.employee_type if user.employee_type is not None else 0,
        "positions": positions,
        "orders": orders,
        "time_zone": user.time_zone or "",
        "custom_attrs": custom_attrs,
        "job_level_id": user.job_level_id or "",
        "job_family_id": user.job_family_id or "",
        "dotted_line_leader_user_ids": list(user.dotted_line_leader_user_ids or []),
    }


class ContactUserUpdatedV3Event(Event):
    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        """Handle contact user updated events."""

        event_data = dispatch_single_event(
            request,
            self.runtime,
            lambda builder: builder.register_p2_contact_user_updated_v3,
        ).event
        if event_data is None:
            raise ValueError("event_data is None")

        current_snapshot = _build_user_snapshot(event_data.object)
        previous_snapshot = _build_user_snapshot(event_data.old_object)

        status = current_snapshot.get("status", {})

        variables_dict: dict[str, Any] = {
            "user_id": current_snapshot.get("user_id", ""),
            "open_id": current_snapshot.get("open_id", ""),
            "union_id": current_snapshot.get("union_id", ""),
            "name": current_snapshot.get("name", ""),
            "en_name": current_snapshot.get("en_name", ""),
            "nickname": current_snapshot.get("nickname", ""),
            "email": current_snapshot.get("email", ""),
            "enterprise_email": current_snapshot.get("enterprise_email", ""),
            "job_title": current_snapshot.get("job_title", ""),
            "mobile": current_snapshot.get("mobile", ""),
            "mobile_visible": current_snapshot.get("mobile_visible", False),
            "gender": current_snapshot.get("gender", 0),
            "leader_user_id": current_snapshot.get("leader_user_id", ""),
            "city": current_snapshot.get("city", ""),
            "country": current_snapshot.get("country", ""),
            "work_station": current_snapshot.get("work_station", ""),
            "join_time": current_snapshot.get("join_time", 0),
            "is_tenant_manager": current_snapshot.get("is_tenant_manager", False),
            "employee_no": current_snapshot.get("employee_no", ""),
            "employee_type": current_snapshot.get("employee_type", 0),
            "time_zone": current_snapshot.get("time_zone", ""),
            "job_level_id": current_snapshot.get("job_level_id", ""),
            "job_family_id": current_snapshot.get("job_family_id", ""),
            "status_is_frozen": status.get("is_frozen", False),
            "status_is_resigned": status.get("is_resigned", False),
            "status_is_activated": status.get("is_activated", False),
            "status_is_exited": status.get("is_exited", False),
            "status_is_unjoin": status.get("is_unjoin", False),
            "department_ids": current_snapshot.get("department_ids", []),
            "positions": current_snapshot.get("positions", []),
            "orders": current_snapshot.get("orders", []),
            "custom_attributes": current_snapshot.get("custom_attrs", []),
            "dotted_line_leader_user_ids": current_snapshot.get("dotted_line_leader_user_ids", []),
            "current_user_json": current_snapshot,
            "previous_user_json": previous_snapshot,
        }

        return Variables(
            variables=variables_dict,
        )
