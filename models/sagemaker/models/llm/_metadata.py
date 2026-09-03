"""Helpers for attaching Dify metadata to SageMaker requests as a request-body field.

SageMaker's plugin uses ``boto3`` and the ``sagemaker.Predictor`` directly
(no OAICompat base class). The ``inference`` function builds a payload
dict and passes it to ``predictor.predict(payload)``. The Dify app_id is
propagated by writing the dify keys into a namespaced payload field
(``_dify_metadata``) when the new ``enable_request_metadata`` credential
is ``"enabled"``.

The namespaced field (``_dify_metadata`` with an underscore-prefixed key)
is used so it doesn't collide with model-specific payload fields. The
SageMaker endpoint is expected to ignore unknown body fields (consistent
with OpenAI-compatible body behavior); the dify metadata is purely for
observability / proxy-side propagation.

Caveats:
- SageMaker endpoints may have strict payload validation and reject
  unknown fields. If your endpoint rejects the `_dify_metadata` field,
  disable the credential (`enable_request_metadata=disabled`). The
  helper never sends the field unless the credential is enabled.
- SageMaker's public endpoint API does not document a custom metadata
  field, so the value is purely for observability / proxy-side
  propagation, identical to the bury-point metadata used in the other
  LLM plugins (anthropic, gemini, stepfun, openai_api_compatible,
  tongyi, volcengine, zhipuai, minimax, cohere, mistralai, deepseek,
  fireworks, ollama, togetherai, moonshot, groq, xai, openrouter).
- The helper never raises; if building the merged metadata fails for
  any reason, the call falls back to a no-op so user requests are not
  blocked.
"""

from __future__ import annotations

from typing import Any

_ENABLED = "enabled"
_METADATA_KEY = "_dify_metadata"
_APP_ID_KEY = "dify_app_id"
_SOURCE_KEY = "dify_source"
_SOURCE_VALUE = "dify"
_MAX_VALUE_LENGTH = 256


def _normalize_metadata_value(s: Any) -> str:
    """Normalize a value into a metadata-safe string.

    Coerces non-string input via ``str()`` so that, e.g., a numeric ``0``
    becomes ``"0"`` rather than being silently dropped by the empty-check,
    and truncates to 256 characters as a hard cap. No character-pattern
    restriction is applied because the SageMaker payload field does not
    document one.
    """
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    if not s:
        return ""
    return s[:_MAX_VALUE_LENGTH]


def build_dify_metadata(app_id: Any) -> dict[str, str] | None:
    """Build the Dify metadata dict, or return ``None``.

    Returns ``None`` if ``app_id`` is ``None`` or the empty string, so
    the caller can skip attaching metadata entirely. Other falsy values
    (e.g. numeric ``0``) are coerced by ``_normalize_metadata_value``
    and pass through. Otherwise, returns a dict with ``dify_app_id``
    (normalized) and a static ``dify_source`` marker.
    """
    if app_id is None or app_id == "":
        return None
    return {
        _APP_ID_KEY: _normalize_metadata_value(app_id),
        _SOURCE_KEY: _SOURCE_VALUE,
    }


def apply_dify_metadata_if_enabled(credentials: dict) -> None:
    """Attach Dify observability metadata to ``credentials[_dify_metadata]`` in place.

    Reads ``credentials['enable_request_metadata']``; when ``"enabled"`` and
    a Dify ``app_id`` resolves from the current session (best-effort),
    writes the Dify ``dify_app_id`` / ``dify_source`` keys into
    ``credentials[_dify_metadata]``. The ``inference`` function then
    merges this dict into the request payload.

    When the credential is disabled, or no ``app_id`` resolves, the
    helper does nothing. The function never raises; if anything goes
    wrong while building the metadata, it falls back to a no-op so the
    user's request still proceeds.
    """
    try:
        if credentials.get("enable_request_metadata") != _ENABLED:
            return
        app_id: str | None = None
        try:
            from dify_plugin import get_current_session

            session = get_current_session()
            if session is not None:
                app_id = getattr(session, "app_id", None)
        except Exception:  # noqa: BLE001, S110 - best-effort telemetry
            pass
        metadata = build_dify_metadata(app_id)
        if metadata is None:
            return
        credentials[_METADATA_KEY] = metadata
    except Exception:  # noqa: BLE001 - telemetry must never break the user request
        # Never block the user's request on metadata wiring.
        return


__all__ = [
    "_normalize_metadata_value",
    "apply_dify_metadata_if_enabled",
    "build_dify_metadata",
]
