from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class IssueRelationRemovedEvent(Event):
    """Linear issue relation removed webhook event."""

    @staticmethod
    def _parse_list_filter(value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def _check_relation_type_filter(self, data: Mapping[str, Any], relation_type_filter: str | None) -> None:
        allowed_types = [item.lower() for item in self._parse_list_filter(relation_type_filter)]
        if not allowed_types:
            return

        relation_type = (data.get("type") or "").lower()
        if not relation_type or relation_type not in allowed_types:
            raise EventIgnoreError()

    def _check_issue_filter(self, data: Mapping[str, Any], issue_filter: str | None) -> None:
        allowed_issue_ids = self._parse_list_filter(issue_filter)
        if not allowed_issue_ids:
            return

        issue_id = (data.get("issueId") or "").strip()
        related_issue_id = (data.get("relatedIssueId") or "").strip()
        if issue_id in allowed_issue_ids or related_issue_id in allowed_issue_ids:
            return

        raise EventIgnoreError()

    def _apply_filters(self, data: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
        self._check_relation_type_filter(data, parameters.get("relation_type_filter"))
        self._check_issue_filter(data, parameters.get("issue_filter"))

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        relation_data = payload.get("data")
        if not relation_data:
            raise ValueError("No issue relation data in payload")

        self._apply_filters(relation_data, parameters)
        return Variables(variables={**payload})
