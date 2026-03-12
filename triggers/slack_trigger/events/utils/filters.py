"""Reusable filter helpers for Slack trigger events.

Each function raises EventIgnoreError when the event does not match the
user-supplied filter value.  If the filter value is empty/None the function
returns immediately so that unset parameters are effectively "no filter".
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.errors.trigger import EventIgnoreError


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_ids(value: Any) -> list[str]:
    """Parse a comma-separated string or list into a cleaned list of IDs."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value).split(",") if v.strip()]


def _extract_channel_id(event: Mapping[str, Any], field: str = "channel") -> str:
    """Extract a channel ID that may be a plain string or an object with an 'id' key."""
    val = event.get(field)
    if isinstance(val, Mapping):
        return str(val.get("id") or "")
    return str(val or "")


# ---------------------------------------------------------------------------
# Filter functions
# ---------------------------------------------------------------------------

def check_channel_id(event: Mapping[str, Any], value: Any, field: str = "channel") -> None:
    """Raise EventIgnoreError if the event channel is not in the allowed list.

    Works for both plain-string channel fields (e.g. channel_archive) and
    nested-object channel fields (e.g. channel_created where channel.id holds
    the ID).  Pass *field* to specify an alternative field name (e.g. "channel_id"
    for pin events).
    """
    allowed = _normalize_ids(value)
    if not allowed:
        return
    channel = _extract_channel_id(event, field)
    if channel not in allowed:
        raise EventIgnoreError()


def check_item_channel_id(event: Mapping[str, Any], value: Any) -> None:
    """Raise EventIgnoreError if the channel in ``event.item.channel`` is not in the allowed list.

    Used for reaction events where the channel is nested inside the ``item``
    object (``event.item.channel``) rather than at the top level.
    """
    allowed = _normalize_ids(value)
    if not allowed:
        return
    item = event.get("item")
    channel = str(item.get("channel") or "") if isinstance(item, Mapping) else ""
    if channel not in allowed:
        raise EventIgnoreError()


def check_user_id(event: Mapping[str, Any], value: Any, field: str = "user") -> None:
    """Raise EventIgnoreError if the event user is not in the allowed list."""
    allowed = _normalize_ids(value)
    if not allowed:
        return
    user = str(event.get(field) or "")
    if user not in allowed:
        raise EventIgnoreError()


def check_text_contains(event: Mapping[str, Any], value: Any) -> None:
    """Raise EventIgnoreError if the message text does not contain *value*."""
    if not value:
        return
    text = str(event.get("text") or "")
    if str(value) not in text:
        raise EventIgnoreError()


def check_bot_filter(event: Mapping[str, Any], value: Any) -> None:
    """Filter messages by bot / human sender.

    Accepted *value* strings:
      - ``"human_only"`` – skip bot messages
      - ``"bot_only"``   – skip human messages
      - anything else / empty – allow all (no filter)

    A message is considered a bot message when the event contains a ``bot_id``
    field or has ``subtype == "bot_message"``.
    """
    if not value or value == "any":
        return
    is_bot = bool(event.get("bot_id")) or event.get("subtype") == "bot_message"
    if value == "human_only" and is_bot:
        raise EventIgnoreError()
    if value == "bot_only" and not is_bot:
        raise EventIgnoreError()


def check_reaction(event: Mapping[str, Any], value: Any) -> None:
    """Raise EventIgnoreError if the emoji reaction is not in the allowed list.

    *value* accepts comma-separated emoji names without colons, e.g. ``"thumbsup,white_check_mark"``.
    """
    allowed = _normalize_ids(value)
    if not allowed:
        return
    reaction = str(event.get("reaction") or "")
    if reaction not in allowed:
        raise EventIgnoreError()


def _check_item_type(event: Mapping[str, Any], value: Any) -> None:
    """Raise EventIgnoreError if ``event.item.type`` does not match *value*."""
    if not value:
        return
    item = event.get("item") or {}
    item_type = str(item.get("type") or "") if isinstance(item, Mapping) else ""
    if item_type != str(value):
        raise EventIgnoreError()


def check_reaction_item_type(event: Mapping[str, Any], value: Any) -> None:
    """Raise EventIgnoreError if the reacted-to item type does not match.

    Slack reports ``item.type`` as one of ``message``, ``file``, or
    ``file_comment``.
    """
    _check_item_type(event, value)


def check_emoji_subtype(event: Mapping[str, Any], value: Any) -> None:
    """Raise EventIgnoreError if the emoji_changed subtype does not match.

    Slack reports ``subtype`` as ``add``, ``remove``, or ``rename``.
    """
    if not value:
        return
    subtype = str(event.get("subtype") or "")
    if subtype != str(value):
        raise EventIgnoreError()


def check_star_item_type(event: Mapping[str, Any], value: Any) -> None:
    """Raise EventIgnoreError if the starred item type does not match.

    Slack reports ``item.type`` as one of ``message``, ``file``, ``channel``,
    ``im``, or ``app``.
    """
    _check_item_type(event, value)
