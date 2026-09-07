"""Helpers for attaching Dify metadata to Fireworks requests as request body.

Fireworks exposes an OpenAI-compatible API via the ``openai`` Python SDK.
``client.chat.completions.create`` accepts an ``extra_body`` parameter that
the SDK forwards as additional JSON fields in the request body. The
Fireworks API is OpenAI-compatible and silently ignores unknown body
fields, so injecting a ``metadata`` field via ``extra_body`` lets us
carry the Dify app_id alongside the rest of the request payload.
Fireworks does not document a character-pattern or length constraint
on metadata values, so this helper only stringifies and truncates the
value to 256 characters as a hard cap.

The merge is non-destructive when the credential is disabled (returns
``None``) and in-place when the credential is enabled and an app_id
resolves (writes back into the input dict and returns the same
reference). The function takes a ``MutableMapping`` so the in-place
mutation contract is part of the type signature.

Session lookup failures are swallowed silently: metadata attachment is
telemetry, and must never break generation if the SDK is missing or
the session context is not initialized.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

_MAX_VALUE_LENGTH = 256


def normalize_metadata_value(s: Any) -> str:
    """Normalize an arbitrary value into a metadata value.

    Coerces non-string input via ``str()`` so that, e.g., a numeric ``0``
    becomes ``"0"`` rather than being silently dropped by the empty-check,
    then truncates to 256 characters. No character-pattern restriction
    is applied because the Fireworks API does not document one.
    """
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    if not s:
        return ""
    return s[:_MAX_VALUE_LENGTH]


def build_dify_metadata(app_id: Any) -> dict[str, str] | None:
    """Build the Dify metadata dict for a Fireworks request, or return ``None``.

    Returns ``None`` if ``app_id`` is ``None`` or the empty string, so
    the caller can skip attaching metadata entirely. Other falsy values
    (e.g. numeric ``0``) are coerced by ``normalize_metadata_value``
    and pass through. Otherwise, returns a dict with ``dify_app_id``
    (normalized) and a static ``dify_source`` marker.
    """
    if app_id is None or app_id == "":
        return None
    return {
        "dify_app_id": normalize_metadata_value(app_id),
        "dify_source": "dify",
    }


def apply_dify_metadata_if_enabled(
    extra_kwargs: MutableMapping[str, Any], credentials: dict
) -> MutableMapping[str, Any] | None:
    """Return an extra_kwargs dict with Dify metadata attached when opt-in is set.

    Reads ``credentials['enable_request_metadata']``; when ``"enabled"``,
    resolves the current Dify session's ``app_id`` (best-effort) and
    writes the Dify keys into ``extra_kwargs['extra_body']['metadata']``.
    If existing ``extra_body`` is present as a dict with a ``metadata``
    field, Dify keys are merged alongside caller-supplied ones; if
    absent (or not a dict), the Dify-only dict is set. The function
    mutates the input in place and also returns the same reference
    for fluent use.

    Returns ``None`` when the credential is disabled or no app_id
    resolves, so the call site can pass ``None`` to the SDK and avoid
    sending an empty ``extra_body`` field. Session lookup failures
    are swallowed silently: metadata attachment is telemetry, and must
    never break generation.
    """
    try:
        if credentials.get("enable_request_metadata") != "enabled":
            return None

        app_id: str | None = None
        try:
            from dify_plugin import get_current_session

            session = get_current_session()
            if session is not None:
                app_id = getattr(session, "app_id", None)
        except Exception:  # noqa: BLE001, S110 - telemetry must never break generation
            # Best-effort telemetry: never break generation.
            pass

        metadata = build_dify_metadata(app_id)
        if metadata is None:
            return None

        existing_extra_body = extra_kwargs.get("extra_body")
        if isinstance(existing_extra_body, dict):
            inner_metadata = existing_extra_body.get("metadata")
            if isinstance(inner_metadata, dict):
                # Preserve any caller-supplied metadata; Dify keys win on collision.
                existing_extra_body["metadata"] = {**inner_metadata, **metadata}
            else:
                # No caller-supplied metadata (or a non-dict placeholder).
                # Overwrite with the Dify dict rather than blow up.
                existing_extra_body["metadata"] = dict(metadata)
        else:
            # No caller-supplied extra_body (or a non-dict placeholder).
            # Set a fresh dict with the Dify metadata.
            extra_kwargs["extra_body"] = {"metadata": dict(metadata)}
        return extra_kwargs
    except Exception:  # noqa: BLE001 - telemetry must never break the user request
        # Never block the user's request on metadata wiring.
        return None


__all__ = [
    "apply_dify_metadata_if_enabled",
    "build_dify_metadata",
    "normalize_metadata_value",
]


__all__ = [
    "apply_dify_metadata_if_enabled",
    "build_dify_metadata",
    "normalize_metadata_value",
]
