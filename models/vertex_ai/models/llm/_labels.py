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
from typing import Optional

_INVALID_CHAR_RE = re.compile(r"[^a-z0-9_-]")
_MAX_LABEL_LENGTH = 63


def normalize_label_value(s: str) -> str:
    """Normalize an arbitrary string into a Vertex AI label-compatible value.

    Lowercases the input, replaces any character outside ``[a-z0-9_-]`` with
    ``_``, and truncates to 63 characters. An empty input returns an empty
    string (no exception raised).
    """
    if not s:
        return ""
    lowered = s.lower()
    sanitized = _INVALID_CHAR_RE.sub("_", lowered)
    return sanitized[:_MAX_LABEL_LENGTH]


def build_dify_labels(app_id: Optional[str]) -> Optional[dict[str, str]]:
    """Build the Dify labels dict for a Vertex AI request, or return ``None``.

    Returns ``None`` if ``app_id`` is ``None`` or an empty string, so the
    caller can skip attaching labels entirely. Otherwise, returns a dict with
    ``dify_app_id`` (normalized) and a static ``dify_source`` marker.
    """
    if not app_id:
        return None
    return {
        "dify_app_id": normalize_label_value(app_id),
        "dify_source": "dify",
    }
