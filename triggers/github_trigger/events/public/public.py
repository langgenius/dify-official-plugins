from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class PublicEvent(Event):
    """Public event (repository made public)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        repo = payload.get("repository")
        if not isinstance(repo, Mapping):
            raise ValueError("No repository in payload")

        repo_filter = parameters.get("repository_name")
        if repo_filter:
            names = {v.strip().lower() for v in str(repo_filter).split(",") if v.strip()}
            full_name = (repo.get("full_name") or "").lower()
            name = (repo.get("name") or "").lower()
            if names and full_name not in names and name not in names:
                raise EventIgnoreError()

        return Variables(variables={**payload})

