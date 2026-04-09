from __future__ import annotations

import fnmatch
from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class PushEvent(Event):
    """GitHub Push Event"""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        self._check_ref(payload, parameters.get("ref"))
        self._check_branch(payload, parameters.get("branch"))
        self._check_pusher(payload, parameters.get("pusher"))
        self._check_deleted(payload, parameters.get("deleted"))
        self._check_forced(payload, parameters.get("forced"))
        self._check_commit_message_contains(payload, parameters.get("commit_message_contains"))
        self._check_files_glob(payload, parameters.get("files_glob"))

        return Variables(variables={**payload})

    def _check_ref(self, payload: Mapping[str, Any], ref_param: str | None) -> None:
        if not ref_param:
            return

        allowed_refs = [ref.strip() for ref in ref_param.split(",") if ref.strip()]
        if not allowed_refs:
            return

        current_ref = payload.get("ref")
        if current_ref not in allowed_refs:
            raise EventIgnoreError()

    def _check_branch(self, payload: Mapping[str, Any], branch_param: str | None) -> None:
        if not branch_param:
            return

        allowed_branches = [branch.strip() for branch in branch_param.split(",") if branch.strip()]
        if not allowed_branches:
            return

        current_ref = payload.get("ref") or ""
        branch = current_ref.split("/", 2)[-1] if current_ref.startswith("refs/heads/") else current_ref
        if branch not in allowed_branches:
            raise EventIgnoreError()

    def _check_pusher(self, payload: Mapping[str, Any], pusher_param: str | None) -> None:
        if not pusher_param:
            return

        allowed_pushers = [pusher.strip() for pusher in pusher_param.split(",") if pusher.strip()]
        if not allowed_pushers:
            return

        pusher = payload.get("pusher", {})
        candidates = {
            pusher.get("name"),
            pusher.get("email"),
            payload.get("sender", {}).get("login"),
        }
        candidates = {candidate for candidate in candidates if candidate}
        if not candidates or not any(candidate in allowed_pushers for candidate in candidates):
            raise EventIgnoreError()

    def _check_deleted(self, payload: Mapping[str, Any], deleted_param: bool | None) -> None:
        if deleted_param is None:
            return

        is_deleted = bool(payload.get("deleted"))
        if is_deleted != bool(deleted_param):
            raise EventIgnoreError()

    def _check_forced(self, payload: Mapping[str, Any], forced_param: bool | None) -> None:
        if forced_param is None:
            return

        is_forced = bool(payload.get("forced"))
        if is_forced != bool(forced_param):
            raise EventIgnoreError()

    def _check_commit_message_contains(self, payload: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return

        keywords = [kw.strip().lower() for kw in str(value).split(",") if kw.strip()]
        if not keywords:
            return

        commits = payload.get("commits") or []
        for commit in commits:
            message = (commit.get("message") or "").lower()
            if any(kw in message for kw in keywords):
                return

        head = payload.get("head_commit") or {}
        message = (head.get("message") or "").lower()
        if any(kw in message for kw in keywords):
            return

        raise EventIgnoreError()

    def _check_files_glob(self, payload: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return

        patterns = [p.strip() for p in str(value).split(",") if p.strip()]
        if not patterns:
            return

        commits = payload.get("commits") or []
        for commit in commits:
            for key in ("added", "modified", "removed"):
                for path in commit.get(key) or []:
                    for pattern in patterns:
                        if fnmatch.fnmatch(path, pattern):
                            return

        raise EventIgnoreError()
