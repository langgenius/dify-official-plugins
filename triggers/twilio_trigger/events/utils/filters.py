"""Common filter utilities for Twilio trigger events."""

from __future__ import annotations

import re
from typing import Any, Mapping

from dify_plugin.errors.trigger import EventIgnoreError


def check_from_filter(from_number: str, filter_str: str | None) -> None:
    """
    Check if the from number is in the allowed list.

    Args:
        from_number: The sender's phone number
        filter_str: Comma-separated list of allowed phone numbers

    Raises:
        TriggerEventIgnoreError: If the from number is not in the allowed list
    """
    if not filter_str:
        return

    allowed = {n.strip() for n in filter_str.split(",") if n.strip()}
    if allowed and from_number not in allowed:
        raise EventIgnoreError(f"From number {from_number} not in allowed list")


def check_body_contains(body: str, keyword: str | None) -> None:
    """
    Check if the message body contains the specified keyword (case-insensitive).

    Args:
        body: The message body
        keyword: The keyword to search for

    Raises:
        EventIgnoreError: If the keyword is not found in the body
    """
    if not keyword:
        return

    if keyword.lower() not in body.lower():
        raise EventIgnoreError(f"Body does not contain keyword: {keyword}")


def check_body_regex(body: str, pattern: str | None) -> None:
    """
    Check if the message body matches the specified regex pattern.

    Args:
        body: The message body
        pattern: The regex pattern to match

    Raises:
        EventIgnoreError: If the body does not match the pattern
    """
    if not pattern:
        return

    try:
        if not re.search(pattern, body):
            raise EventIgnoreError(f"Body does not match regex: {pattern}")
    except re.error as e:
        raise EventIgnoreError(f"Invalid regex pattern: {e}")


def check_call_status(status: str, allowed_statuses: str | None) -> None:
    """
    Check if the call status is in the allowed list.

    Args:
        status: The call status
        allowed_statuses: Comma-separated list of allowed statuses

    Raises:
        EventIgnoreError: If the status is not in the allowed list
    """
    if not allowed_statuses:
        return

    allowed = {s.strip().lower() for s in allowed_statuses.split(",") if s.strip()}
    if allowed and status.lower() not in allowed:
        raise EventIgnoreError(f"Call status {status} not in allowed list")


def check_profile_name(profile_name: str | None, filter_str: str | None) -> None:
    """
    Check if the WhatsApp profile name matches the filter.

    Args:
        profile_name: The sender's WhatsApp profile name
        filter_str: Comma-separated list of allowed profile names

    Raises:
        EventIgnoreError: If the profile name is not in the allowed list
    """
    if not filter_str:
        return

    if not profile_name:
        raise EventIgnoreError("Profile name is empty but filter is set")

    allowed = {n.strip().lower() for n in filter_str.split(",") if n.strip()}
    if allowed and profile_name.lower() not in allowed:
        raise EventIgnoreError(f"Profile name {profile_name} not in allowed list")


def apply_message_filters(
    payload: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> None:
    """
    Apply common message filters (SMS and WhatsApp).

    Args:
        payload: The Twilio webhook payload
        parameters: The event parameters from configuration

    Raises:
        EventIgnoreError: If any filter condition is not met
    """
    from_number = payload.get("From", "")
    body = payload.get("Body", "")

    check_from_filter(from_number, parameters.get("from_filter"))
    check_body_contains(body, parameters.get("body_contains"))
    check_body_regex(body, parameters.get("body_regex"))
