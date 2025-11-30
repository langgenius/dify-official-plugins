from __future__ import annotations

import fnmatch
from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.errors.trigger import EventIgnoreError

from .common import ensure_action, load_json_payload, require_mapping


def load_pull_request_payload(
    request: Request,
    *,
    expected_action: str | None = None,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Load payload and pull request object, enforcing expected action."""
    payload = load_json_payload(request)
    ensure_action(payload, expected_action)
    pull_request = require_mapping(payload, "pull_request")
    return payload, pull_request


def apply_pull_request_common_filters(pull_request: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
    """Apply standard pull request filters based on configuration parameters."""
    check_base_branch(pull_request, parameters.get("base_branch"))
    check_head_branch(pull_request, parameters.get("head_branch"))
    check_author(pull_request, parameters.get("author"))
    check_draft_state(pull_request, parameters.get("draft"))
    check_labels(pull_request, parameters.get("label_names"))
    check_reviewers(pull_request, parameters.get("reviewers"))
    check_pr_size_threshold(pull_request, parameters.get("pr_size_threshold"))
    check_changed_files_glob(pull_request, parameters.get("changed_files_glob"))


def check_base_branch(pull_request: Mapping[str, Any], value: Any) -> None:
    branches = _normalize_list(value)
    if not branches:
        return

    current = pull_request.get("base", {}).get("ref")
    if current not in branches:
        raise EventIgnoreError()


def check_head_branch(pull_request: Mapping[str, Any], value: Any) -> None:
    branches = _normalize_list(value)
    if not branches:
        return

    current = pull_request.get("head", {}).get("ref")
    if current not in branches:
        raise EventIgnoreError()


def check_author(pull_request: Mapping[str, Any], value: Any) -> None:
    authors = _normalize_list(value)
    if not authors:
        return

    author = pull_request.get("user", {}).get("login")
    if author not in authors:
        raise EventIgnoreError()


def check_draft_state(pull_request: Mapping[str, Any], value: Any) -> None:
    if value is None:
        return

    is_draft = bool(pull_request.get("draft"))
    if is_draft != bool(value):
        raise EventIgnoreError()


def check_labels(pull_request: Mapping[str, Any], value: Any) -> None:
    labels = _normalize_list(value)
    if not labels:
        return

    current = [label.get("name") for label in pull_request.get("labels", [])]
    if not any(label in current for label in labels):
        raise EventIgnoreError()


def check_reviewers(pull_request: Mapping[str, Any], value: Any) -> None:
    reviewers = _normalize_list(value)
    if not reviewers:
        return

    requested: list[str] = []
    for reviewer in pull_request.get("requested_reviewers", []) or []:
        login = reviewer.get("login")
        if login:
            requested.append(login)
    for team in pull_request.get("requested_teams", []) or []:
        slug = team.get("slug")
        if slug:
            requested.append(slug)

    if not requested or not any(r in requested for r in reviewers):
        raise EventIgnoreError()


def check_merged_state(pull_request: Mapping[str, Any], value: Any) -> None:
    if value is None:
        return

    is_merged = bool(pull_request.get("merged"))
    if is_merged != bool(value):
        raise EventIgnoreError()


def check_pr_size_threshold(pull_request: Mapping[str, Any], value: Any) -> None:
    """Filter by PR size: additions+deletions must be <= threshold.

    If threshold cannot be parsed or counts are missing, this filter is ignored.
    """
    if value in (None, ""):
        return

    try:
        threshold = int(str(value).strip())
    except ValueError:
        return

    additions = pull_request.get("additions")
    deletions = pull_request.get("deletions")
    if isinstance(additions, int) and isinstance(deletions, int):
        total = additions + deletions
        if total > threshold:
            raise EventIgnoreError()


def check_changed_files_glob(pull_request: Mapping[str, Any], value: Any) -> None:
    """Filter by changed file patterns.

    This requires file paths to be present in the payload. If not present,
    the filter is skipped gracefully.
    Supported payload keys: 'files' (list[str]) or 'changed_files_detail' (list[Mapping] with 'filename').
    Multiple patterns can be provided (comma-separated).
    """
    patterns = _normalize_list(value)
    if not patterns:
        return

    file_paths: list[str] = []
    raw_files = pull_request.get("files")
    if isinstance(raw_files, list):
        for item in raw_files:
            if isinstance(item, str):
                file_paths.append(item)
            elif isinstance(item, Mapping) and isinstance(item.get("filename"), str):
                file_paths.append(item.get("filename"))

    if not file_paths:
        details = pull_request.get("changed_files_detail")
        if isinstance(details, list):
            for entry in details:
                if isinstance(entry, Mapping) and isinstance(entry.get("filename"), str):
                    file_paths.append(entry.get("filename"))

    if not file_paths:
        # Cannot evaluate; skip filter
        return

    matched = False
    for path in file_paths:
        for pattern in patterns:
            if fnmatch.fnmatch(path, pattern):
                matched = True
                break
        if matched:
            break

    if not matched:
        raise EventIgnoreError()


def _normalize_list(raw: Any) -> list[str]:
    if raw is None:
        return []

    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]

    return [item.strip() for item in str(raw).split(",") if item.strip()]
