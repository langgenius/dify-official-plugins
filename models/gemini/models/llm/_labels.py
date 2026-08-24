"""Helpers for attaching Dify metadata to Gemini requests as labels.

The Gemini API (``google-genai`` SDK) accepts a ``labels`` field on
``GenerateContentConfig``. The values are surfaced in the Cloud Billing
breakdown and Cloud Logging for per-app cost and usage attribution.
Constraints, from the Google Cloud documentation:

  - Keys must begin with a lowercase letter.
  - Keys and values may contain only lowercase letters, digits, underscores,
    and hyphens.
  - Keys and values must be 63 characters or less.

UUIDs (36 characters, lowercase hex with hyphens) already satisfy these
constraints. ``normalize_label_value`` exists as a safety net for any
non-UUID value (e.g. emails, non-ASCII text) that may flow through in the
future.
"""

from __future__ import annotations

import re
from typing import Any, Optional

_INVALID_CHAR_RE = re.compile(r"[^a-z0-9_-]")
_MAX_LABEL_LENGTH = 63


def normalize_label_value(s: Any) -> str:
    """Normalize an arbitrary value into a Gemini label-compatible value.

    Lowercases the input, replaces any character outside ``[a-z0-9_-]`` with
    ``_``, and truncates to 63 characters. An empty input returns an empty
    string (no exception raised). Non-string inputs are coerced via ``str()``
    first so that, e.g., a numeric ``0`` becomes ``"0"`` rather than being
    silently dropped by the empty-check.
    """
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    if not s:
        return ""
    # Truncate first to bound the cost of lower()/sub() on pathological input.
    # lower() can still expand certain Unicode chars, so re-truncate at the end.
    s = s[:_MAX_LABEL_LENGTH]
    lowered = s.lower()
    sanitized = _INVALID_CHAR_RE.sub("_", lowered)
    return sanitized[:_MAX_LABEL_LENGTH]


def build_dify_labels(app_id: Any) -> Optional[dict[str, str]]:
    """Build the Dify labels dict for a Gemini request, or return ``None``.

    Returns ``None`` if ``app_id`` is ``None`` or an empty string, so the
    caller can skip attaching labels entirely. Other falsy values (e.g.
    numeric ``0``) are coerced by ``normalize_label_value`` and pass
    through. Otherwise, returns a dict with ``dify_app_id`` (normalized)
    and a static ``dify_source`` marker.
    """
    if app_id is None or app_id == "":
        return None
    return {
        "dify_app_id": normalize_label_value(app_id),
        "dify_source": "dify",
    }


def apply_dify_labels_if_enabled(config: Any, credentials: dict) -> None:
    """Inject Dify labels into a ``GenerateContentConfig`` when opt-in is set.

    Reads ``credentials['enable_request_metadata']``; when ``"enabled"``,
    resolves the current Dify session's ``app_id`` (best-effort) and writes
    the built labels into ``config.labels``. If existing labels are present
    as a dict, Dify keys are merged in alongside caller-supplied ones; if
    absent (or not a dict), the Dify-only dict is set.

    Session lookup failures are swallowed silently: label attachment is
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

    labels = build_dify_labels(app_id)
    if labels is None:
        return

    existing = getattr(config, "labels", None)
    if isinstance(existing, dict):
        # Preserve any caller-supplied labels; only fill in Dify keys.
        # Build a new dict rather than mutating in place, so a caller-shared
        # reference is never modified as a side effect of telemetry opt-in.
        config.labels = {**existing, **labels}
    else:
        config.labels = labels
