"""Utility functions for Zendesk ticket event filtering."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.errors.trigger import EventIgnoreError


def check_status(ticket: Mapping[str, Any], allowed_statuses: str | None) -> None:
    """Check if ticket status matches allowed statuses."""
    if not allowed_statuses:
        return

    current_status = ticket.get("status")
    if not current_status:
        return

    statuses = [s.strip().lower() for s in allowed_statuses.split(",")]
    if current_status.lower() not in statuses:
        raise EventIgnoreError()


def check_priority(ticket: Mapping[str, Any], allowed_priorities: str | None) -> None:
    """Check if ticket priority matches allowed priorities."""
    if not allowed_priorities:
        return

    current_priority = ticket.get("priority")
    if not current_priority:
        return

    priorities = [p.strip().lower() for p in allowed_priorities.split(",")]
    if current_priority.lower() not in priorities:
        raise EventIgnoreError()


def check_tags(ticket: Mapping[str, Any], required_tags: str | None) -> None:
    """Check if ticket has all required tags."""
    if not required_tags:
        return

    ticket_tags = ticket.get("tags", [])
    if not isinstance(ticket_tags, list):
        raise EventIgnoreError()

    required = [t.strip().lower() for t in required_tags.split(",")]
    ticket_tags_lower = [t.lower() for t in ticket_tags]

    for tag in required:
        if tag not in ticket_tags_lower:
            raise EventIgnoreError()


def check_assignee(ticket: Mapping[str, Any], allowed_assignees: str | None) -> None:
    """Check if ticket assignee matches allowed assignees."""
    if not allowed_assignees:
        return

    assignee_id = ticket.get("assignee_id")
    if assignee_id is None:
        raise EventIgnoreError()

    allowed = [a.strip() for a in allowed_assignees.split(",")]
    if str(assignee_id) not in allowed:
        raise EventIgnoreError()


def check_group(ticket: Mapping[str, Any], allowed_groups: str | None) -> None:
    """Check if ticket group matches allowed groups."""
    if not allowed_groups:
        return

    group_id = ticket.get("group_id")
    if group_id is None:
        raise EventIgnoreError()

    allowed = [g.strip() for g in allowed_groups.split(",")]
    if str(group_id) not in allowed:
        raise EventIgnoreError()


def check_subject_contains(ticket: Mapping[str, Any], keywords: str | None) -> None:
    """Check if ticket subject contains any of the keywords."""
    if not keywords:
        return

    subject = ticket.get("subject", "")
    if not subject:
        raise EventIgnoreError()

    keywords_list = [k.strip().lower() for k in keywords.split(",")]
    subject_lower = subject.lower()

    for keyword in keywords_list:
        if keyword in subject_lower:
            return

    raise EventIgnoreError()


def check_description_contains(ticket: Mapping[str, Any], keywords: str | None) -> None:
    """Check if ticket description contains any of the keywords."""
    if not keywords:
        return

    description = ticket.get("description", "")
    if not description:
        raise EventIgnoreError()

    keywords_list = [k.strip().lower() for k in keywords.split(",")]
    description_lower = description.lower()

    for keyword in keywords_list:
        if keyword in description_lower:
            return

    raise EventIgnoreError()


def check_requester(ticket: Mapping[str, Any], allowed_requesters: str | None) -> None:
    """Check if ticket requester matches allowed requesters."""
    if not allowed_requesters:
        return

    requester_id = ticket.get("requester_id")
    if requester_id is None:
        raise EventIgnoreError()

    allowed = [r.strip() for r in allowed_requesters.split(",")]
    if str(requester_id) not in allowed:
        raise EventIgnoreError()


def check_type(ticket: Mapping[str, Any], allowed_types: str | None) -> None:
    """Check if ticket type matches allowed types."""
    if not allowed_types:
        return

    ticket_type = ticket.get("type")
    if not ticket_type:
        return

    types = [t.strip().lower() for t in allowed_types.split(",")]
    if ticket_type.lower() not in types:
        raise EventIgnoreError()
