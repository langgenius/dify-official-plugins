from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.errors.trigger import EventIgnoreError
from werkzeug import Request

from .common import ensure_action, load_json_payload, require_mapping


def load_pull_request_review_payload(
    request: Request,
    *,
    expected_action: str | None = None,
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    """Load payload, review, and pull request data for review events."""
    payload = load_json_payload(request)
    ensure_action(payload, expected_action)

    review = require_mapping(payload, "review")
    pull_request = require_mapping(payload, "pull_request")
    return payload, review, pull_request


def apply_pull_request_review_filters(
    review: Mapping[str, Any],
    pull_request: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> None:
    check_review_state(review, parameters.get("review_state"))
    check_reviewer(review, parameters.get("reviewer"))
    check_pull_request_author(pull_request, parameters.get("author"))
    check_pull_request_numbers(pull_request, parameters.get("pull_request_numbers"))
    check_review_body(review, parameters.get("body_contains"))


def check_review_state(review: Mapping[str, Any], value: Any) -> None:
    states = _normalize_list(value)
    if not states:
        return

    current = (review.get("state") or "").lower()
    if current not in states:
        raise EventIgnoreError()


def check_reviewer(review: Mapping[str, Any], value: Any) -> None:
    reviewers = _normalize_list(value)
    if not reviewers:
        return

    reviewer = review.get("user", {}).get("login")
    if reviewer not in reviewers:
        raise EventIgnoreError()


def check_pull_request_author(pull_request: Mapping[str, Any], value: Any) -> None:
    authors = _normalize_list(value)
    if not authors:
        return

    author = pull_request.get("user", {}).get("login")
    if author not in authors:
        raise EventIgnoreError()


def check_pull_request_numbers(pull_request: Mapping[str, Any], value: Any) -> None:
    numbers = _normalize_list(value)
    if not numbers:
        return

    number = str(pull_request.get("number"))
    if number not in numbers:
        raise EventIgnoreError()


def check_review_body(review: Mapping[str, Any], value: Any) -> None:
    keywords = _normalize_list(value, lowercase=True)
    if not keywords:
        return

    body = (review.get("body") or "").lower()
    if not any(keyword in body for keyword in keywords):
        raise EventIgnoreError()


def check_dismissed_by(payload: Mapping[str, Any], value: Any) -> None:
    users = _normalize_list(value)
    if not users:
        return

    actor = payload.get("sender", {}).get("login")
    if actor not in users:
        raise EventIgnoreError()


def check_dismissal_message(payload: Mapping[str, Any], value: Any) -> None:
    keywords = _normalize_list(value, lowercase=True)
    if not keywords:
        return

    message = (payload.get("dismissal_message") or "").lower()
    if not any(keyword in message for keyword in keywords):
        raise EventIgnoreError()


def _normalize_list(raw: Any, *, lowercase: bool = False) -> list[str]:
    if raw is None:
        return []

    if isinstance(raw, (list, tuple)):
        values = [str(item).strip() for item in raw if str(item).strip()]
    else:
        values = [item.strip() for item in str(raw).split(",") if item.strip()]

    if lowercase:
        values = [value.lower() for value in values]

    return values
