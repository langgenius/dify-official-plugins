"""Utility functions for Zendesk ticket event filtering."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.errors.trigger import EventIgnoreError

ZENDESK_DOMAIN_SUFFIX = ".zendesk.com"


def normalize_subdomain(value: Any) -> str:
    """Accept `acme`, `acme.zendesk.com` or `https://acme.zendesk.com/` and return `acme`."""
    subdomain = str(value or "").strip().lower()
    subdomain = re.sub(r"^https?://", "", subdomain).split("/", 1)[0]
    if subdomain.endswith(ZENDESK_DOMAIN_SUFFIX):
        subdomain = subdomain[: -len(ZENDESK_DOMAIN_SUFFIX)]
    return subdomain


def load_payload(request: Request, payload: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """Prefer the payload decoded by the dispatcher, fall back to the raw request body."""
    data = payload or request.get_json(force=True, silent=True)
    if not isinstance(data, Mapping) or not data:
        raise ValueError("No payload received")
    return data


def get_ticket(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    ticket = payload.get("detail")
    if not isinstance(ticket, Mapping):
        raise ValueError("Invalid ticket data in payload")
    return ticket


def get_event(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    event = payload.get("event")
    return event if isinstance(event, Mapping) else {}


def split_csv(value: Any) -> list[str]:
    """Split a comma separated parameter into lower-cased, non-empty items."""
    if not value:
        return []
    return [item.strip().lower() for item in str(value).split(",") if item.strip()]


def lower(value: Any) -> str:
    return str(value).lower() if value is not None else ""


def build_ticket_url(subdomain: Any, ticket_id: Any) -> str | None:
    subdomain = normalize_subdomain(subdomain)
    if not subdomain or ticket_id in (None, ""):
        return None
    return f"https://{subdomain}{ZENDESK_DOMAIN_SUFFIX}/agent/tickets/{ticket_id}"


def resolve_subdomain(runtime: Any) -> str:
    """Read the Zendesk subdomain from subscription properties or provider credentials."""
    subscription = getattr(runtime, "subscription", None)
    properties = getattr(subscription, "properties", None) or {}
    credentials = getattr(runtime, "credentials", None) or {}
    return normalize_subdomain(properties.get("subdomain") or credentials.get("subdomain"))


def check_value_in(value: Any, allowed: str | None) -> None:
    """Ignore the event unless `value` is one of the comma separated `allowed` values."""
    allowed_values = split_csv(allowed)
    if allowed_values and lower(value) not in allowed_values:
        raise EventIgnoreError()


def check_status(ticket: Mapping[str, Any], allowed_statuses: str | None) -> None:
    """Check if ticket status matches allowed statuses."""
    check_value_in(ticket.get("status"), allowed_statuses)


def check_priority(ticket: Mapping[str, Any], allowed_priorities: str | None) -> None:
    """Check if ticket priority matches allowed priorities."""
    check_value_in(ticket.get("priority"), allowed_priorities)


def check_type(ticket: Mapping[str, Any], allowed_types: str | None) -> None:
    """Check if ticket type matches allowed types."""
    check_value_in(ticket.get("type"), allowed_types)


def check_tags(ticket: Mapping[str, Any], required_tags: str | None) -> None:
    """Check if ticket has all required tags."""
    required = split_csv(required_tags)
    if not required:
        return

    ticket_tags = ticket.get("tags") or []
    if not isinstance(ticket_tags, list):
        raise EventIgnoreError()

    ticket_tags_lower = {lower(tag) for tag in ticket_tags}
    if any(tag not in ticket_tags_lower for tag in required):
        raise EventIgnoreError()


def check_contains(text: Any, keywords: str | None) -> None:
    """Ignore the event unless `text` contains at least one of the comma separated keywords."""
    keywords_list = split_csv(keywords)
    if keywords_list and not any(keyword in lower(text) for keyword in keywords_list):
        raise EventIgnoreError()


def check_subject_contains(ticket: Mapping[str, Any], keywords: str | None) -> None:
    """Check if ticket subject contains any of the keywords."""
    check_contains(ticket.get("subject"), keywords)


def check_description_contains(ticket: Mapping[str, Any], keywords: str | None) -> None:
    """Check if ticket description contains any of the keywords."""
    check_contains(ticket.get("description"), keywords)


def check_assignee(ticket: Mapping[str, Any], allowed_assignees: str | None) -> None:
    """Check if ticket assignee matches allowed assignees."""
    check_value_in(ticket.get("assignee_id"), allowed_assignees)


def check_group(ticket: Mapping[str, Any], allowed_groups: str | None) -> None:
    """Check if ticket group matches allowed groups."""
    check_value_in(ticket.get("group_id"), allowed_groups)


def check_requester(ticket: Mapping[str, Any], allowed_requesters: str | None) -> None:
    """Check if ticket requester matches allowed requesters."""
    check_value_in(ticket.get("requester_id"), allowed_requesters)


def check_bool(value: Any, expected: Any) -> None:
    """Filter by a select parameter whose options are `any`, `true` and `false`."""
    expected = lower(expected or "any")
    if expected == "any":
        return
    if bool(value) != (expected == "true"):
        raise EventIgnoreError()
