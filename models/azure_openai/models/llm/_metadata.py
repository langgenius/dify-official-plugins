"""Helpers for attaching Dify metadata to OpenAI chat/responses requests.

OpenAI's ``chat.completions.create`` and ``responses.create`` accept a
``metadata`` field (a string-to-string map) that — when the account has
Stored Completions enabled — surfaces in the Usage Dashboard, enabling
per-app filtering. Constraints, from the OpenAI API reference:

  Set of 16 key-value pairs that can be attached to an object. Keys are
  strings with a maximum length of 64 characters. Values are strings with
  a maximum length of 512 characters.

Unlike Bedrock or Vertex, OpenAI does not document a character pattern
restriction on metadata values, so ``normalize_metadata_value`` only
enforces string coercion and the 512-character length cap.

The OpenAI/Azure OpenAI API only accepts ``metadata`` when ``store`` is
true — it rejects the request with ``BadRequestError: The 'metadata'
parameter is only allowed when 'store' is enabled.`` otherwise. Enabling
this feature therefore inherently requires ``store=true``, so
``apply_dify_metadata_if_enabled`` sets it alongside the metadata. This
means requests and responses are persisted to Stored Completions on the
Azure OpenAI resource; the credential's help text documents that storage
behavior. An explicit ``store`` value already present on the request is
respected rather than overwritten.
"""

from __future__ import annotations

from typing import Any, Optional

_MAX_VALUE_LENGTH = 512


def normalize_metadata_value(s: Any) -> str:
    """Normalize an arbitrary value into an OpenAI metadata value.

    Coerces non-string input via ``str()`` so that, e.g., a numeric ``0``
    becomes ``"0"`` rather than being silently dropped by the empty-check,
    then truncates to 512 characters. OpenAI does not document a
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
    """Build the Dify metadata dict for an OpenAI request, or return ``None``.

    Returns ``None`` if ``app_id`` is ``None`` or an empty string, so the
    caller can skip attaching metadata entirely. Other falsy values (e.g.
    numeric ``0``) are coerced by ``normalize_metadata_value`` and pass
    through. Otherwise, returns a dict with ``dify_app_id`` (normalized)
    and a static ``dify_source`` marker.
    """
    if app_id is None or app_id == "":
        return None
    return {
        "dify_app_id": normalize_metadata_value(app_id),
        "dify_source": "dify",
    }


def apply_dify_metadata_if_enabled(target: dict, credentials: dict) -> None:
    """Inject Dify metadata into ``target`` when opt-in credential is set.

    Reads ``credentials['enable_request_metadata']``; when ``"enabled"``,
    resolves the current Dify session's ``app_id`` (best-effort), sets
    ``target['metadata']`` to the built dict (if one is produced), and sets
    ``target['store'] = True`` — the API only accepts ``metadata`` when
    ``store`` is enabled. An explicit ``store`` value already on ``target``
    is left untouched.

    Session lookup failures are swallowed silently: metadata attachment is
    telemetry, and must never break generation if the SDK is missing or
    the session context is not initialized.
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
    # The API only accepts metadata when store=true. Don't overwrite an
    # explicit store value already set by the caller.
    if "store" not in target:
        target["store"] = True
