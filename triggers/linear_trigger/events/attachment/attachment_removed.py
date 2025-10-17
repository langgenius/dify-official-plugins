from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class AttachmentRemovedEvent(Event):
    """Linear attachment removed webhook event."""

    @staticmethod
    def _parse_list_filter(value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def _check_title_contains(self, data: Mapping[str, Any], title_contains: str | None) -> None:
        keywords = [keyword.lower() for keyword in self._parse_list_filter(title_contains)]
        if not keywords:
            return

        title = (data.get("title") or "").lower()
        if not any(keyword in title for keyword in keywords):
            raise EventIgnoreError()

    def _check_source_type_filter(self, data: Mapping[str, Any], source_type_filter: str | None) -> None:
        allowed_sources = self._parse_list_filter(source_type_filter)
        if not allowed_sources:
            return

        source_type = (data.get("sourceType") or "").strip()
        if not source_type or source_type not in allowed_sources:
            raise EventIgnoreError()

    def _check_issue_filter(self, data: Mapping[str, Any], issue_filter: str | None) -> None:
        allowed_issue_ids = self._parse_list_filter(issue_filter)
        if not allowed_issue_ids:
            return

        issue_id = (data.get("issueId") or "").strip()
        if not issue_id or issue_id not in allowed_issue_ids:
            raise EventIgnoreError()

    def _apply_filters(self, data: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
        self._check_title_contains(data, parameters.get("title_contains"))
        self._check_source_type_filter(data, parameters.get("source_type_filter"))
        self._check_issue_filter(data, parameters.get("issue_filter"))

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        attachment_data = payload.get("data")
        if not attachment_data:
            raise ValueError("No attachment data in payload")

        self._apply_filters(attachment_data, parameters)
        return Variables(variables={**payload})
