"""Helpers for attaching Dify metadata to Anthropic Messages requests.

The Anthropic Messages API accepts a ``metadata`` object on each call. The
official typed schema (``anthropic.types.MetadataParam``)
only declares ``user_id``, but the underlying API accepts arbitrary
string-to-string keys, which surface in the Anthropic admin console for
per-app cost and usage attribution. Constraints:

  - Values must be strings.
  - ``user_id`` is documented at <=256 characters; the API does not publish
    per-key length limits for other fields, so values are capped at 256
    characters as a safe default.

Unlike Bedrock, Anthropic does not document a character pattern restriction
on metadata values, so ``normalize_metadata_value`` only enforces string
coercion and the 256-character length cap.

Session lookup failures are swallowed silently: metadata attachment is
telemetry, and must never break generation if the SDK is missing or the
session context is not initialized.
"""

from __future__ import annotations

from typing import Any, Optional

_MAX_VALUE_LENGTH = 256


def normalize_metadata_value(s: Any) -> str:
    """Normalize an arbitrary value into an Anthropic metadata value.

    Coerces non-string input via ``str()`` so that, e.g., a numeric ``0``
    becomes ``"0"`` rather than being silently dropped by the empty-check,
    then truncates to 256 characters. Anthropic does not document a
    character-pattern restriction, so no character substitution is
    performed.
    """
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    if not s:
        return ""
    return s[:_MAX_VALUE_LENGTH]


def build_dify_metadata(app_id: Any) -> Optional[dict[str, str]]:
    """Build the Dify metadata dict for an Anthropic request, or return ``None``.

    Returns ``None`` if ``app_id`` is ``None`` or an empty string, so the
    caller can skip attaching metadata entirely. Other falsy values (e.g.
    numeric ``0``) are coerced by ``normalize_metadata_value`` and pass
    through. Otherwise, returns a dict with ``dify_app_id`` (normalized)
    and a static ``dify_source`` marker.
    """
    if app_id is None or app_id == "":
        return None
    return {"dify_app_id": normalize_metadata_value(app_id), "dify_source": "dify"}


def apply_dify_metadata_if_enabled(target: dict, credentials: dict) -> None:
    """Inject Dify metadata into ``target`` when the opt-in credential is set.

    Reads ``credentials['enable_request_metadata']``; when ``"enabled"``,
    resolves the current Dify session's ``app_id`` (best-effort) and writes
    ``target['metadata']`` to a dict that carries the built Dify keys
    (when one is produced). If ``target['metadata']`` already holds a
    dict, the Dify keys are merged on top rather than overwriting the
    existing value; if the existing value is not a dict, the Dify keys
    take over.

    Session lookup failures are swallowed silently: metadata is
    best-effort telemetry, and must never break generation.
    """
    if credentials.get("enable_request_metadata") != "enabled":
        return

    app_id: Optional[str] = None
    try:
        from dify_plugin import get_current_session

        session = get_current_session()
        if session is not None:
            app_id = getattr(session, "app_id", None)
    except Exception:
        # Best-effort telemetry: never break generation.
        pass

    metadata = build_dify_metadata(app_id)
    if metadata is None:
        return

    existing = target.get("metadata")
    if isinstance(existing, dict):
        # Preserve any caller-supplied metadata; only fill in Dify keys.
        # Build a new dict rather than mutating in place, so a caller-shared
        # reference is never modified as a side effect of telemetry opt-in.
        target["metadata"] = {**existing, **metadata}
    else:
        target["metadata"] = metadata
