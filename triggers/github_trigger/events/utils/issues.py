from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.errors.trigger import EventIgnoreError


def check_labels(issue: Mapping[str, Any], value: Any) -> None:
    labels = _normalize_list(value)
    if not labels:
        return
    current = [lbl.get("name") for lbl in issue.get("labels", [])]
    if not any(lbl in current for lbl in labels):
        raise EventIgnoreError()


def check_assignee(issue: Mapping[str, Any], value: Any) -> None:
    assignees = _normalize_list(value)
    if not assignees:
        return
    assigned = {assignee.get("login") for assignee in issue.get("assignees", [])}
    single = issue.get("assignee") or {}
    if login := single.get("login"):
        assigned.add(login)
    if not assigned or not any(a in assigned for a in assignees):
        raise EventIgnoreError()


def check_authors(issue: Mapping[str, Any], value: Any) -> None:
    authors = _normalize_list(value)
    if not authors:
        return
    login = (issue.get("user") or {}).get("login")
    if login not in authors:
        raise EventIgnoreError()


def check_milestone(issue: Mapping[str, Any], value: Any) -> None:
    milestones = _normalize_list(value)
    if not milestones:
        return
    milestone = (issue.get("milestone") or {}).get("title")
    if milestone not in milestones:
        raise EventIgnoreError()


def check_title_contains(issue: Mapping[str, Any], value: Any) -> None:
    keywords = _normalize_list(value, lowercase=True)
    if not keywords:
        return
    title = (issue.get("title") or "").lower()
    if not any(k in title for k in keywords):
        raise EventIgnoreError()


def check_body_contains(issue: Mapping[str, Any], value: Any) -> None:
    keywords = _normalize_list(value, lowercase=True)
    if not keywords:
        return
    body = (issue.get("body") or "").lower()
    if not any(k in body for k in keywords):
        raise EventIgnoreError()


def check_state(issue: Mapping[str, Any], value: Any) -> None:
    if not value:
        return
    state = (issue.get("state") or "").lower()
    targets = {s.strip().lower() for s in str(value).split(",") if s.strip()}
    if targets and state not in targets:
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

