"""Optional Dify request headers for ChatGLM.

The headers are for proxy-side observability; ChatGLM does not document them.
"""

from __future__ import annotations

from typing import Any

_ENABLED = "enabled"
_APP_ID_HEADER = "X-Dify-App-Id"
_SOURCE_HEADER = "X-Dify-Source"
_SOURCE_VALUE = "dify"
_MAX_VALUE_LENGTH = 256


def _normalize_header_value(s: Any) -> str:
    """Normalize a value into a header-safe string.

    Coerces non-string input via ``str()`` so that, e.g., a numeric ``0``
    becomes ``"0"`` rather than being silently dropped by the empty-check,
    strips CR/LF and other control characters (``urllib3`` rejects them
    with ``InvalidHeader``), and truncates to 256 characters as a hard
    cap.
    """
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    if not s:
        return ""
    # Strip CR/LF and other control characters; keep visible ASCII only.
    s = "".join(ch for ch in s if 0x20 <= ord(ch) <= 0x7E)
    if not s:
        return ""
    return s[:_MAX_VALUE_LENGTH]


def build_dify_headers(app_id: Any) -> dict[str, str]:
    """Build the Dify header dict, or return an empty dict.

    Returns an empty dict if the resolved ``app_id`` is missing or
    normalizes to the empty string, so the caller can skip attaching
    metadata entirely.
    """
    app_id_normalized = _normalize_header_value(app_id)
    if not app_id_normalized:
        return {}
    return {
        _APP_ID_HEADER: app_id_normalized,
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


def apply_dify_headers_if_enabled(credentials: dict) -> None:
    """Attach Dify observability headers to ``credentials['extra_headers']`` in place.

    Reads ``credentials['enable_request_metadata']``; when ``"enabled"`` and
    ``credentials['app_id']`` resolves to a non-empty string, writes the
    Dify ``X-Dify-App-Id`` / ``X-Dify-Source`` headers into
    ``credentials['extra_headers']``. Existing entries on
    ``credentials['extra_headers']`` are preserved; on collision the Dify
    keys win so the helper always controls its own observability markers.

    When the credential is disabled, or no ``app_id`` resolves, the
    helper does nothing. The function never raises; if anything goes
    wrong while building the headers, it falls back to a no-op so the
    user's request still proceeds.
    """
    try:
        if credentials.get("enable_request_metadata") != _ENABLED:
            return
        app_id = credentials.get("app_id")
        headers = build_dify_headers(app_id)
        if not headers:
            return
        existing = credentials.get("extra_headers")
        if existing is None:
            credentials["extra_headers"] = headers
            return
        # Merge: copy to avoid mutating the caller's dict reference, and
        # let Dify keys override any existing collision so the helper
        # always controls its own observability markers.
        merged = dict(existing)
        merged.update(headers)
        credentials["extra_headers"] = merged
    except Exception:  # noqa: BLE001 - telemetry must never break the user request
        # Never block the user's request on metadata wiring.
        return


__all__ = [
    "_normalize_header_value",
    "apply_dify_headers_if_enabled",
    "build_dify_headers",
]
