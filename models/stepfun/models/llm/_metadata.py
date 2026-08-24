"""Helpers for attaching Dify metadata to StepFun requests as headers.

StepFun exposes an OpenAI-compatible API via ``dify_plugin``'s
``OAICompatLargeLanguageModel`` base class. The base class does not
forward a body-level ``metadata`` field to the upstream request (the
underlying OpenAI SDK is not used directly here), so this plugin routes
the Dify app_id through the ``extra_headers`` credential instead. The
``OAICompatLargeLanguageModel._generate`` path already merges
``credentials['extra_headers']`` into the outbound request, so the
headers are carried through with no SDK change required.

Header values are constrained to visible ASCII (0x20-0x7E inclusive) so
urllib3 never rejects the request with ``InvalidHeader`` on CR/LF or
other control characters. Values are truncated to 256 characters as
a hard cap (UUID app_ids are 36 chars, so the cap is a safety net rather
than a real bound).

Session lookup failures are swallowed silently: header attachment is
telemetry, and must never break generation if the SDK is missing or the
session context is not initialized.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

_MAX_HEADER_LENGTH = 256


def normalize_header_value(s: Any) -> str:
    """Normalize an arbitrary value into a header value.

    Coerces non-string input via ``str()`` so that, e.g., a numeric ``0``
    becomes ``"0"`` rather than being silently dropped by the empty-check,
    strips CR/LF and other control characters (urllib3 rejects them with
    ``InvalidHeader``), strips leading/trailing whitespace, and truncates
    to 256 characters. Whitespace-only and all-control-character inputs
    collapse to an empty string so the caller can skip header injection.
    """
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    # Restrict to visible ASCII; drop everything else, including CR/LF
    # and other control characters that would cause urllib3 to raise
    # InvalidHeader on outbound requests.
    s = "".join(ch for ch in s if 0x20 <= ord(ch) <= 0x7E).strip()
    if not s:
        return ""
    return s[:_MAX_HEADER_LENGTH]


def build_dify_headers(app_id: Any) -> Optional[dict[str, str]]:
    """Build the Dify header dict for a StepFun request, or return ``None``.

    Returns ``None`` if ``app_id`` is ``None``, the empty string, or
    normalizes to an empty string (e.g. whitespace-only or all-control
    characters), so the caller can skip attaching headers entirely.
    Other falsy values (e.g. numeric ``0``) are coerced by
    ``normalize_header_value`` and pass through. Otherwise, returns a
    dict with ``X-Dify-App-Id`` (normalized) and a static
    ``X-Dify-Source`` marker.
    """
    normalized = normalize_header_value(app_id)
    if not normalized:
        return None
    return {
        "X-Dify-App-Id": normalized,
        "X-Dify-Source": "dify",
    }


def apply_dify_headers_if_enabled(credentials: dict) -> dict:
    """Return a credentials copy with Dify headers attached when opt-in is set.

    Reads ``credentials['enable_request_metadata']``; when ``"enabled"``,
    resolves the current Dify session's ``app_id`` (best-effort) and
    returns a shallow-copied credentials dict with the Dify headers merged
    into ``credentials['extra_headers']``. The function always returns a
    new mapping (never the input reference) so callers can rely on the
    no-mutation contract regardless of the credential state.

    Existing ``extra_headers`` are preserved alongside the Dify keys.
    The merge is case-insensitive on keys: any caller-supplied header
    whose lower-case name matches a Dify key is dropped before the Dify
    keys are written, so the upstream request carries exactly one header
    per logical name. The Dify keys take precedence because the merge
    writes them last.

    Session lookup failures are swallowed silently: header attachment is
    telemetry, and must never break generation.
    """
    if credentials.get("enable_request_metadata") != "enabled":
        # Always return a new dict for predictability; callers can rely
        # on the no-mutation contract regardless of branch.
        return dict(credentials)

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
        return dict(credentials)

    existing = credentials.get("extra_headers")
    if isinstance(existing, Mapping):
        # Drop any caller-supplied keys whose lower-case name matches a
        # Dify key, so the request carries exactly one header per
        # logical name (HTTP header names are case-insensitive).
        dify_keys_lower = {k.lower() for k in headers}
        merged = {
            k: v for k, v in existing.items() if k.lower() not in dify_keys_lower
        }
        merged.update(headers)
    else:
        merged = dict(headers)
    return {**credentials, "extra_headers": merged}
