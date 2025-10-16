from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.errors.trigger import EventIgnoreError
from werkzeug import Request

from .common import ensure_action, load_json_payload, require_mapping


def load_pull_request_review_comment_payload(
    request: Request,
    *,
    expected_action: str | None = None,
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    """Load payload, comment, and pull request data for review comment events."""
    payload = load_json_payload(request)
    ensure_action(payload, expected_action)

    comment = require_mapping(payload, "comment")
    pull_request = require_mapping(payload, "pull_request")
    return payload, comment, pull_request


def apply_pull_request_review_comment_filters(
    comment: Mapping[str, Any],
    pull_request: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> None:
    check_comment_body(comment, parameters.get("body_contains"))
    check_commenter(comment, parameters.get("commenter"))
    check_path(comment, parameters.get("path"))
    check_position(comment, parameters.get("position"))
    check_pull_request_author(pull_request, parameters.get("author"))
    check_pull_request_numbers(pull_request, parameters.get("pull_request_numbers"))


def check_comment_body(comment: Mapping[str, Any], value: Any) -> None:
    keywords = _normalize_list(value, lowercase=True)
    if not keywords:
        return

    body = (comment.get("body") or "").lower()
    if not any(keyword in body for keyword in keywords):
        raise EventIgnoreError()


def check_commenter(comment: Mapping[str, Any], value: Any) -> None:
    commenters = _normalize_list(value)
    if not commenters:
        return

    commenter = comment.get("user", {}).get("login")
    if commenter not in commenters:
        raise EventIgnoreError()


def check_path(comment: Mapping[str, Any], value: Any) -> None:
    paths = _normalize_list(value)
    if not paths:
        return

    path = comment.get("path") or comment.get("original_path")
    if path not in paths:
        raise EventIgnoreError()


def check_position(comment: Mapping[str, Any], value: Any) -> None:
    if value in (None, ""):
        return

    try:
        target_positions = {int(item.strip()) for item in str(value).split(",") if item.strip()}
    except ValueError:
        raise EventIgnoreError() from None

    positions = {
        position
        for position in (
            comment.get("position"),
            comment.get("original_position"),
            comment.get("line"),
            comment.get("original_line"),
        )
        if isinstance(position, int)
    }

    if not positions or not (positions & target_positions):
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


def check_comment_deleter(payload: Mapping[str, Any], value: Any) -> None:
    deleters = _normalize_list(value)
    if not deleters:
        return

    actor = payload.get("sender", {}).get("login")
    if actor not in deleters:
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
