from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class RepositoryUnifiedEvent(Event):
    """Unified Repository event (created/deleted/archived/unarchived/publicized/privatized/renamed/transferred/edited)."""

    _KNOWN_ACTIONS = {
        "created",
        "deleted",
        "archived",
        "unarchived",
        "publicized",
        "privatized",
        "renamed",
        "transferred",
        "edited",
    }

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = set(parameters.get("actions") or [])
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        if action and action not in self._KNOWN_ACTIONS:
            # forward-compatibility: if GitHub adds new actions, allow pass-through
            pass

        repo = payload.get("repository")
        if not isinstance(repo, Mapping):
            raise ValueError("No repository in payload")

        name_contains = parameters.get("name_contains")
        if name_contains:
            keywords = [v.strip().lower() for v in str(name_contains).split(",") if v.strip()]
            full_name = (repo.get("full_name") or "").lower()
            name = (repo.get("name") or "").lower()
            if keywords and not any(k in full_name or k in name for k in keywords):
                raise EventIgnoreError()

        visibility_filter = parameters.get("visibility")
        if visibility_filter:
            allowed = {v.strip().lower() for v in str(visibility_filter).split(",") if v.strip()}
            visibility = (repo.get("visibility") or ("private" if repo.get("private") else "public")).lower()
            if allowed and visibility not in allowed:
                raise EventIgnoreError()

        return Variables(variables={**payload})

