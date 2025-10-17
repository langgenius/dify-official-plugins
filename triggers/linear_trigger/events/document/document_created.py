from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class DocumentCreatedEvent(Event):
    """
    Linear Document Created Event

    This event transforms Linear document created webhook events and extracts relevant
    information from the webhook payload to provide as variables to the workflow.
    """

    def _check_title_contains(self, document_data: Mapping[str, Any], title_contains: str | None) -> None:
        """Check if document title contains required keywords"""
        if not title_contains:
            return

        keywords = [keyword.strip().lower() for keyword in title_contains.split(",") if keyword.strip()]
        if not keywords:
            return

        title = (document_data.get("title") or "").lower()
        if not any(keyword in title for keyword in keywords):
            raise EventIgnoreError()

    def _check_project_only(self, document_data: Mapping[str, Any], project_only: bool) -> None:
        """Check if document is associated with a project when project_only filter is enabled"""
        if not project_only:
            return

        # Document must have projectId to be considered a project document
        project_id = document_data.get("projectId")
        if not project_id:
            raise EventIgnoreError()

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Transform Linear document created webhook event into structured Variables
        """
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        # Get document data
        document_data = payload.get("data")
        if not document_data:
            raise ValueError("No document data in payload")

        # Apply filters
        self._check_title_contains(document_data, parameters.get("title_contains"))
        self._check_project_only(document_data, parameters.get("project_only", False))

        # Return full payload as variables
        return Variables(variables={**payload})
