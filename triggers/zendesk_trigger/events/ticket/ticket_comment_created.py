from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event

from ..utils import build_ticket_url, check_bool, get_event, get_ticket, load_payload, lower, resolve_subdomain


class TicketCommentCreatedEvent(Event):
    """Triggered when a comment is added to a Zendesk ticket (`zen:event-type:ticket.comment_added`)."""

    def _on_event(
        self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any] | None = None
    ) -> Variables:
        payload = load_payload(request, payload)
        ticket = get_ticket(payload)

        comment = get_event(payload).get("comment")
        if not isinstance(comment, Mapping):
            raise ValueError("Invalid comment data in payload")
        author = comment.get("author") if isinstance(comment.get("author"), Mapping) else {}

        check_bool(comment.get("is_public", True), parameters.get("is_public"))
        check_bool(author.get("is_staff"), parameters.get("author_is_staff"))

        body = str(comment.get("body") or "")
        keywords = [keyword.strip() for keyword in str(parameters.get("body_contains") or "").split(",")]
        keywords = [keyword for keyword in keywords if keyword]
        matched_keyword = next((keyword for keyword in keywords if keyword.lower() in body.lower()), None)
        if keywords and matched_keyword is None:
            raise EventIgnoreError()

        clean_body = body
        if matched_keyword and lower(parameters.get("strip_keyword") or "true") == "true":
            clean_body = re.sub(re.escape(matched_keyword), "", body, count=1, flags=re.IGNORECASE).strip()

        ticket_id = ticket.get("id")
        return Variables(
            variables={
                "comment": comment,
                "ticket": ticket,
                "ticket_id": str(ticket_id) if ticket_id is not None else None,
                "ticket_url": build_ticket_url(resolve_subdomain(self.runtime), ticket_id),
                "matched_keyword": matched_keyword,
                "clean_body": clean_body,
            }
        )
