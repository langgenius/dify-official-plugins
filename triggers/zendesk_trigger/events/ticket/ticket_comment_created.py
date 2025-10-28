from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class TicketCommentCreatedEvent(Event):
    """Triggered when a comment is added to a Zendesk ticket."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        comment = payload.get("event", {}).get("comment", {})
        if not isinstance(comment, Mapping):
            raise ValueError("Invalid comment data in payload")

        # Filter by public/private
        is_public_param = parameters.get("is_public", "any")
        if is_public_param != "any":
            comment_is_public = comment.get("is_public", True)
            expected_public = is_public_param == "true"
            if comment_is_public != expected_public:
                raise EventIgnoreError()

        # Filter by body content
        body_contains = parameters.get("body_contains")
        if body_contains:
            body = comment.get("body", "")
            if not body:
                raise EventIgnoreError()

            keywords = [k.strip().lower() for k in body_contains.split(",")]
            body_lower = body.lower()

            found = False
            for keyword in keywords:
                if keyword in body_lower:
                    found = True
                    break

            if not found:
                raise EventIgnoreError()

        ticket = payload.get("detail", {})
        if not isinstance(ticket, Mapping):
            ticket = {}

        return Variables(variables={"comment": comment, "ticket": ticket})
