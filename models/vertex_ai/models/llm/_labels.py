"""Helpers for attaching Dify metadata to Vertex AI requests as labels.

Vertex AI accepts request-level labels that are forwarded to Cloud Billing,
enabling per-app cost breakdown. Label keys and values must satisfy the
constraints documented here:

  https://cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1/projects.locations.publishers.models/generateContent

Specifically: keys and values must be 63 characters or less, contain only
lowercase letters, digits, underscores, and hyphens, and keys must begin with
a lowercase letter.

UUIDs (36 characters, lowercase hex with hyphens) already satisfy these
constraints. ``normalize_label_value`` exists as a safety net for any non-UUID
value (e.g. emails, non-ASCII text) that may flow through in the future.
"""

from __future__ import annotations

import re
from typing import Any, Optional

_INVALID_CHAR_RE = re.compile(r"[^a-z0-9_-]")
_MAX_LABEL_LENGTH = 63


def normalize_label_value(s: Any) -> str:
    """Normalize an arbitrary value into a Vertex AI label-compatible value.

    Lowercases the input, replaces any character outside ``[a-z0-9_-]`` with
    ``_``, and truncates to 63 characters. An empty input returns an empty
    string (no exception raised). Non-string inputs are coerced via ``str()``
    first so that, e.g., a numeric ``0`` becomes ``"0"`` rather than being
    silently dropped by the empty-check.
    """
    if not isinstance(s, str):
        s = str(s)
    if not s:
        return ""
    lowered = s.lower()
    sanitized = _INVALID_CHAR_RE.sub("_", lowered)
    return sanitized[:_MAX_LABEL_LENGTH]


def build_dify_labels(app_id: Any) -> Optional[dict[str, str]]:
    """Build the Dify labels dict for a Vertex AI request, or return ``None``.

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


def apply_dify_labels_if_enabled(config_kwargs: dict, credentials: dict) -> None:
    """Inject Dify labels into ``config_kwargs`` when opt-in credential is set.

    Reads ``credentials['enable_request_metadata']``; when ``"enabled"``,
    resolves the current Dify session's ``app_id`` (best-effort) and merges
    the built labels into ``config_kwargs['labels']``. If existing labels
    are present as a dict, Dify keys are merged in alongside caller-supplied
    ones; if absent (or not a dict), the Dify-only dict is set.

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
    existing = config_kwargs.get("labels")
    if isinstance(existing, dict):
        # Preserve any caller-supplied labels; only fill in Dify keys.
        existing.update(labels)
    else:
        config_kwargs["labels"] = labels
