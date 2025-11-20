from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.errors.trigger import EventIgnoreError


def load_json_payload(request: Request) -> Mapping[str, Any]:
    """Load JSON payload from request, raising if missing."""
    payload = request.get_json()
    if not payload:
        raise ValueError("No payload received")
    return payload


def ensure_action(payload: Mapping[str, Any], expected_action: str | None) -> None:
    """Ensure payload action matches expected."""
    if not expected_action:
        return

    if payload.get("action") != expected_action:
        raise EventIgnoreError()


def require_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Require that payload contains a mapping under given key."""
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"No {key} data in payload")
    return value
