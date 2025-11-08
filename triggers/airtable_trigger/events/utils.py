"""Utility functions for Airtable event filtering."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.errors.trigger import EventIgnoreError


def check_table_id(record_metadata: Mapping[str, Any], allowed_table_ids: str | None) -> None:
    """Check if record's table matches allowed table IDs."""
    if not allowed_table_ids:
        return

    table_id = record_metadata.get("tableId")
    if not table_id:
        return

    allowed = [tid.strip() for tid in allowed_table_ids.split(",") if tid.strip()]
    if table_id not in allowed:
        raise EventIgnoreError()


def check_field_changed(changed_fields: list[str] | None, required_fields: str | None) -> None:
    """Check if any of the required fields were changed."""
    if not required_fields:
        return

    if not changed_fields:
        raise EventIgnoreError()

    required = [f.strip() for f in required_fields.split(",") if f.strip()]
    changed_set = set(changed_fields)

    for field in required:
        if field in changed_set:
            return

    raise EventIgnoreError()


def check_field_contains(fields: Mapping[str, Any], field_name: str | None, keywords: str | None) -> None:
    """Check if a field contains any of the keywords."""
    if not keywords or not field_name:
        return

    field_value = fields.get(field_name)
    if not field_value:
        raise EventIgnoreError()

    # Convert to string for searching
    field_str = str(field_value).lower()
    keywords_list = [k.strip().lower() for k in keywords.split(",") if k.strip()]

    for keyword in keywords_list:
        if keyword in field_str:
            return

    raise EventIgnoreError()
