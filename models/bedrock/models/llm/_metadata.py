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
from typing import Optional

_INVALID_CHAR_RE = re.compile(r"[^a-zA-Z0-9\s:_@$#=/+,\-.]")
_MAX_VALUE_LENGTH = 256


def normalize_metadata_value(s: str) -> str:
    """Normalize an arbitrary string into a Bedrock requestMetadata value.

    Replaces any character outside the allowed set
    ``[a-zA-Z0-9\\s:_@$#=/+,-.]`` with ``_`` and truncates to 256
    characters. Case is preserved (Bedrock allows mixed case). An empty
    input returns an empty string.
    """
    if not s:
        return ""
    sanitized = _INVALID_CHAR_RE.sub("_", s)
    return sanitized[:_MAX_VALUE_LENGTH]


def build_dify_request_metadata(app_id: Optional[str]) -> Optional[dict[str, str]]:
    """Build the Dify requestMetadata dict for a Bedrock request, or return ``None``.

    Returns ``None`` if ``app_id`` is ``None`` or an empty string, so the
    caller can skip attaching metadata entirely. Otherwise, returns a dict
    with ``dify_app_id`` (normalized) and a static ``dify_source`` marker.
    """
    if not app_id:
        return None
    return {
        "dify_app_id": normalize_metadata_value(app_id),
        "dify_source": "dify",
    }
