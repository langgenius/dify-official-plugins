from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.errors.trigger import EventIgnoreError


def check_comment_body_contains(comment: Mapping[str, Any], value: Any) -> None:
    keywords = _normalize_list(value, lowercase=True)
    if not keywords:
        return
    body = (comment.get("body") or "").lower()
    if not any(k in body for k in keywords):
        raise EventIgnoreError()


def check_commenter(comment: Mapping[str, Any], value: Any) -> None:
    commenters = _normalize_list(value)
    if not commenters:
        return
    login = (comment.get("user") or {}).get("login")
    if login not in commenters:
        raise EventIgnoreError()


def check_issue_labels(issue: Mapping[str, Any], value: Any) -> None:
    labels = _normalize_list(value)
    if not labels:
        return
    current = [lbl.get("name") for lbl in issue.get("labels", [])]
    if not any(lbl in current for lbl in labels):
        raise EventIgnoreError()


def check_issue_state(issue: Mapping[str, Any], value: Any) -> None:
    if not value:
        return
    state = (issue.get("state") or "").lower()
    targets = {s.strip().lower() for s in str(value).split(",") if s.strip()}
    if targets and state not in targets:
        raise EventIgnoreError()


def check_is_pull_request(issue: Mapping[str, Any], flag: Any) -> None:
    if flag is None:
        return
    is_pr = "pull_request" in issue
    if bool(flag) != is_pr:
        raise EventIgnoreError()


def _normalize_list(raw: Any, *, lowercase: bool = False) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        values = [str(x).strip() for x in raw if str(x).strip()]
    else:
        values = [x.strip() for x in str(raw).split(",") if x.strip()]
    if lowercase:
        values = [v.lower() for v in values]
    return values
