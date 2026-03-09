"""Filter helpers for Notion webhook events.

Each helper raises ``EventIgnoreError`` when the filter criterion is not met.
All helpers are no-ops when the caller passes an empty / falsy ``value``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.errors.trigger import EventIgnoreError


def _normalize_ids(value: Any) -> list[str]:
    """Return a list of stripped, non-empty ID strings from a comma-separated string or list."""
    if not value:
        return []
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _get_parent(entity_content: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(entity_content, Mapping):
        return {}
    parent = entity_content.get("parent")
    return parent if isinstance(parent, Mapping) else {}


def check_parent_type(entity_content: Mapping[str, Any] | None, value: Any) -> None:
    """Filter by parent type.

    Notion parent.type values: ``"workspace"``, ``"database_id"``, ``"page_id"``, ``"block_id"``.
    The ``value`` parameter accepts the same strings as Notion returns, e.g. ``"database_id"``.
    Leave blank to accept all.
    """
    if not value:
        return
    parent = _get_parent(entity_content)
    parent_type = parent.get("type") or ""
    if parent_type != str(value).strip():
        raise EventIgnoreError()


def check_parent_id(entity_content: Mapping[str, Any] | None, value: Any) -> None:
    """Filter by the parent's ID (database_id, page_id, or block_id).

    Notion stores the parent ID under a key that matches the parent type, e.g.
    ``parent.database_id``, ``parent.page_id``, ``parent.block_id``.
    Accepts comma-separated IDs; passes if any match.
    """
    allowed = _normalize_ids(value)
    if not allowed:
        return
    parent = _get_parent(entity_content)
    parent_type = parent.get("type") or ""
    parent_id = parent.get(parent_type) or ""
    if not parent_id or parent_id not in allowed:
        raise EventIgnoreError()


def check_author_id(entity_content: Mapping[str, Any] | None, value: Any) -> None:
    """Filter by the ID of the user who created the entity (created_by.id).

    Accepts comma-separated user IDs; passes if any match.
    """
    allowed = _normalize_ids(value)
    if not allowed:
        return
    if not isinstance(entity_content, Mapping):
        raise EventIgnoreError()
    created_by = entity_content.get("created_by")
    author_id = (created_by.get("id") if isinstance(created_by, Mapping) else None) or ""
    if not author_id or author_id not in allowed:
        raise EventIgnoreError()


def check_text_contains(entity_content: Mapping[str, Any] | None, value: Any) -> None:
    """Filter comment events by whether any rich_text segment contains *value*.

    Case-insensitive substring match against the ``plain_text`` of each segment.
    """
    if not value:
        return
    if not isinstance(entity_content, Mapping):
        raise EventIgnoreError()
    needle = str(value).lower()
    rich_text = entity_content.get("rich_text")
    if not isinstance(rich_text, list):
        raise EventIgnoreError()
    for segment in rich_text:
        if isinstance(segment, Mapping):
            plain = segment.get("plain_text") or ""
            if needle in plain.lower():
                return
    raise EventIgnoreError()
