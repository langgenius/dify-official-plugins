"""Helpers for attaching Dify metadata to StepFun requests as headers.

StepFun exposes an OpenAI-compatible API via ``dify_plugin``'s
``OAICompatLargeLanguageModel`` base class. The base class does not
forward a body-level ``metadata`` field to the upstream request (the
underlying OpenAI SDK is not used directly here), so this plugin routes
the Dify app_id through the ``extra_headers`` credential instead. The
``OAICompatLargeLanguageModel._generate`` path already merges
``credentials['extra_headers']`` into the outbound request, so the
headers are carried through with no SDK change required.

The header values are kept short (the underlying HTTP layer imposes no
documented limit, but the convention is 64-256 characters). The values
are sanitized by simple stringification; no character-pattern restriction
is applied because the header is consumed only by the StepFun server
side, not by the public OpenAI metadata field.

Session lookup failures are swallowed silently: header attachment is
telemetry, and must never break generation if the SDK is missing or the
session context is not initialized.
"""

from __future__ import annotations

from typing import Any, Optional

_MAX_HEADER_LENGTH = 256


def normalize_header_value(s: Any) -> str:
    """Normalize an arbitrary value into a header value.

    Coerces non-string input via ``str()`` so that, e.g., a numeric ``0``
    becomes ``"0"`` rather than being silently dropped by the empty-check,
    then truncates to 256 characters. No character-pattern restriction
    is applied.
    """
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    if not s:
        return ""
    return s[:_MAX_HEADER_LENGTH]


def build_dify_headers(app_id: Any) -> Optional[dict[str, str]]:
    """Build the Dify header dict for a StepFun request, or return ``None``.

    Returns ``None`` if ``app_id`` is ``None`` or an empty string, so the
    caller can skip attaching headers entirely. Other falsy values (e.g.
    numeric ``0``) are coerced by ``normalize_header_value`` and pass
    through. Otherwise, returns a dict with ``X-Dify-App-Id`` (normalized)
    and a static ``X-Dify-Source`` marker.
    """
    if app_id is None or app_id == "":
        return None
    return {
        "X-Dify-App-Id": normalize_header_value(app_id),
        "X-Dify-Source": "dify",
    }


def apply_dify_headers_if_enabled(credentials: dict) -> dict:
    """Return a credentials copy with Dify headers attached when opt-in is set.

    Reads ``credentials['enable_request_metadata']``; when ``"enabled"``,
    resolves the current Dify session's ``app_id`` (best-effort) and
    returns a shallow-copied credentials dict with the Dify headers merged
    into ``credentials['extra_headers']``. If no headers are produced, the
    original credentials reference is returned unchanged (no copy, no
    mutation). Existing ``extra_headers`` are preserved alongside the
    Dify keys, with the Dify keys taking precedence on collision because
    the merge writes Dify keys after the caller's.

    Session lookup failures are swallowed silently: header attachment is
    telemetry, and must never break generation.
    """
    if credentials.get("enable_request_metadata") != "enabled":
        return credentials

    app_id: Optional[str] = None
    try:
        from dify_plugin import get_current_session

        session = get_current_session()
        if session is not None:
            app_id = getattr(session, "app_id", None)
    except Exception:
        # Best-effort telemetry: never break generation.
        pass

    headers = build_dify_headers(app_id)
    if headers is None:
        return credentials

    existing = credentials.get("extra_headers")
    if isinstance(existing, dict):
        # Preserve any caller-supplied headers; only fill in Dify keys.
        # Build a new dict rather than mutating in place, so a caller-shared
        # reference is never modified as a side effect of telemetry opt-in.
        merged = {**existing, **headers}
    else:
        merged = dict(headers)
    return {**credentials, "extra_headers": merged}
