from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class ReleasePublishedEvent(Event):
    """GitHub Release Published Event"""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        if payload.get("action") != "published":
            raise EventIgnoreError()

        release = payload.get("release")
        if not isinstance(release, Mapping):
            raise ValueError("No release data in payload")

        self._check_tag_name(release, parameters.get("tag_name"))
        self._check_prerelease(release, parameters.get("prerelease"))
        self._check_draft(release, parameters.get("draft"))
        self._check_target_branch(release, parameters.get("target_branch"))
        self._check_creator(payload, parameters.get("creator"))

        return Variables(variables={**payload})

    def _check_tag_name(self, release: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        names = [v.strip() for v in value.split(",") if v.strip()]
        if not names:
            return
        tag = (release.get("tag_name") or "").strip()
        if tag not in names:
            raise EventIgnoreError()

    def _check_prerelease(self, release: Mapping[str, Any], value: Any) -> None:
        if value is None:
            return
        is_pre = bool(release.get("prerelease"))
        if is_pre != bool(value):
            raise EventIgnoreError()

    def _check_draft(self, release: Mapping[str, Any], value: Any) -> None:
        if value is None:
            return
        is_draft = bool(release.get("draft"))
        if is_draft != bool(value):
            raise EventIgnoreError()

    def _check_target_branch(self, release: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        branches = [v.strip() for v in value.split(",") if v.strip()]
        if not branches:
            return
        target = (release.get("target_commitish") or "").strip()
        if target not in branches:
            raise EventIgnoreError()

    def _check_creator(self, payload: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        users = [v.strip() for v in value.split(",") if v.strip()]
        if not users:
            return
        actor = payload.get("sender", {}).get("login")
        if actor not in users:
            raise EventIgnoreError()
