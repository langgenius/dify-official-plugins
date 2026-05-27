"""Helpers for attaching Dify metadata to Bedrock Converse API requests.

Amazon Bedrock's Converse / ConverseStream API accepts a ``requestMetadata``
field (a string-to-string map) that is forwarded to CloudWatch invocation
logs, enabling per-app cost and usage tracking. Constraints, from the
Converse API reference:

  https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html

  Map Entries: Maximum number of 16.
  Key   length 1-256, pattern: [a-zA-Z0-9\\s:_@$#=/+,-.]{1,256}
  Value length 0-256, pattern: [a-zA-Z0-9\\s:_@$#=/+,-.]{0,256}

UUIDs (lowercase hex with hyphens, 36 chars) already satisfy these
constraints. ``normalize_metadata_value`` exists as a safety net for any
non-UUID value (e.g. emails, non-ASCII text) that may flow through.
"""

from __future__ import annotations

import re
from typing import Any, Optional

_INVALID_CHAR_RE = re.compile(r"[^a-zA-Z0-9\s:_@$#=/+,\-.]")
_MAX_VALUE_LENGTH = 256


def normalize_metadata_value(s: Any) -> str:
    """Normalize an arbitrary value into a Bedrock requestMetadata value.

    Replaces any character outside the allowed set
    ``[a-zA-Z0-9\\s:_@$#=/+,-.]`` with ``_`` and truncates to 256
    characters. Case is preserved (Bedrock allows mixed case). An empty
    input returns an empty string. Non-string inputs are coerced via
    ``str()`` first so that, e.g., a numeric ``0`` becomes ``"0"`` rather
    than being silently dropped by the empty-check.
    """
    if not isinstance(s, str):
        s = str(s)
    if not s:
        return ""
    # Truncate first to bound the cost of the regex sub() on pathological input.
    # sub() preserves length 1:1, so a single trailing truncation is unnecessary.
    s = s[:_MAX_VALUE_LENGTH]
    return _INVALID_CHAR_RE.sub("_", s)


def build_dify_request_metadata(app_id: Any) -> Optional[dict[str, str]]:
    """Build the Dify requestMetadata dict for a Bedrock request, or return ``None``.

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


def apply_dify_request_metadata_if_enabled(parameters: dict, credentials: dict) -> None:
    """Inject Dify requestMetadata into ``parameters`` when opt-in credential is set.

    Reads ``credentials['enable_request_metadata']``; when ``"enabled"``,
    resolves the current Dify session's ``app_id`` (best-effort) and merges
    the built metadata into ``parameters['requestMetadata']``. If existing
    metadata is present as a dict, Dify keys are merged in alongside
    caller-supplied ones; if absent (or not a dict), the Dify-only dict is
    set.

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

    request_metadata = build_dify_request_metadata(app_id)
    if request_metadata is None:
        return
    existing = parameters.get("requestMetadata")
    if isinstance(existing, dict):
        # Preserve any caller-supplied metadata; only fill in Dify keys.
        existing.update(request_metadata)
    else:
        parameters["requestMetadata"] = request_metadata
