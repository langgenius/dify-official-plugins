from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class CustomerNeedRemovedEvent(Event):
    """Linear customer need removed webhook event."""

    @staticmethod
    def _parse_list(value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _parse_int_list(value: str | None) -> list[int]:
        parsed: list[int] = []
        if not value:
            return parsed
        for item in value.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                parsed.append(int(item))
            except ValueError:
                continue
        return parsed

    def _check_body_contains(self, data: Mapping[str, Any], body_contains: str | None) -> None:
        keywords = [keyword.lower() for keyword in self._parse_list(body_contains)]
        if not keywords:
            return

        body = (data.get("body") or "").lower()
        if not any(keyword in body for keyword in keywords):
            raise EventIgnoreError()

    def _check_priority_filter(self, data: Mapping[str, Any], priority_filter: str | None) -> None:
        allowed_priorities = self._parse_int_list(priority_filter)
        if not allowed_priorities:
            return

        priority = data.get("priority")
        try:
            numeric_priority = int(priority)
        except (TypeError, ValueError):
            raise EventIgnoreError()

        if numeric_priority not in allowed_priorities:
            raise EventIgnoreError()

    def _check_customer_filter(self, data: Mapping[str, Any], customer_filter: str | None) -> None:
        allowed_customers = self._parse_list(customer_filter)
        if not allowed_customers:
            return

        customer_id = (data.get("customerId") or "").strip()
        if not customer_id or customer_id not in allowed_customers:
            raise EventIgnoreError()

    def _check_issue_filter(self, data: Mapping[str, Any], issue_filter: str | None) -> None:
        allowed_issue_ids = self._parse_list(issue_filter)
        if not allowed_issue_ids:
            return

        issue_id = (data.get("issueId") or "").strip()
        if not issue_id or issue_id not in allowed_issue_ids:
            raise EventIgnoreError()

    def _check_project_filter(self, data: Mapping[str, Any], project_filter: str | None) -> None:
        allowed_projects = self._parse_list(project_filter)
        if not allowed_projects:
            return

        project_id = (data.get("projectId") or "").strip()
        if not project_id or project_id not in allowed_projects:
            raise EventIgnoreError()

    def _check_creator_filter(self, data: Mapping[str, Any], creator_filter: str | None) -> None:
        allowed_creators = self._parse_list(creator_filter)
        if not allowed_creators:
            return

        creator_id = (data.get("creatorId") or "").strip()
        if not creator_id or creator_id not in allowed_creators:
            raise EventIgnoreError()

    def _apply_filters(self, data: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
        self._check_body_contains(data, parameters.get("body_contains"))
        self._check_priority_filter(data, parameters.get("priority_filter"))
        self._check_customer_filter(data, parameters.get("customer_filter"))
        self._check_issue_filter(data, parameters.get("issue_filter"))
        self._check_project_filter(data, parameters.get("project_filter"))
        self._check_creator_filter(data, parameters.get("creator_filter"))

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        need_data = payload.get("data")
        if not need_data:
            raise ValueError("No customer need data in payload")

        self._apply_filters(need_data, parameters)
        return Variables(variables={**payload})
