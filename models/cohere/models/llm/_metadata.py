"""Helpers for attaching Dify metadata to Cohere SDK requests.

The Cohere Python SDK (v5.x) does not expose a top-level ``metadata``
argument on ``Client.chat()`` / ``Client.generate()``; it does, however,
expose ``RequestOptions(additional_headers=...)`` which the underlying
HTTP client forwards on every request. That is the same path the rest
of the Cohere SDK uses for SDK-internal headers, so it is the most
stable way to attach observability metadata that lives outside the
JSON body and survives ``cohere.Client`` reconnect / retry.

The helper is opt-in: when the credential ``enable_request_metadata`` is
not set to the literal string ``"enabled"``, the helper returns a
``RequestOptions`` equivalent to ``RequestOptions(max_retries=0)`` so
behavior is unchanged. When enabled, the helper builds a
``RequestOptions(max_retries=0, additional_headers=...)`` with the
``X-Dify-App-Id`` (sourced from ``credentials["app_id"]``) and
``X-Dify-Source: dify`` headers.

Caveats:
- Cohere's public API does not document these headers today, so the
  value is purely for observability / proxy-side propagation, identical
  to the bury-point headers used in the other LLM plugins (anthropic,
  gemini, stepfun, openai_api_compatible, tongyi, volcengine, zhipuai,
  minimax).
- The helper never raises; if building the merged options fails for any
  reason, the call falls back to the original ``RequestOptions(max_retries=0)``
  so user requests are not blocked.
"""

from __future__ import annotations

from cohere.core import RequestOptions

_ENABLED = "enabled"
_APP_ID_HEADER = "X-Dify-App-Id"
_SOURCE_HEADER = "X-Dify-Source"
_SOURCE_VALUE = "dify"


def build_cohere_request_options(credentials: dict) -> RequestOptions:
    """Return a ``RequestOptions`` for the Cohere SDK.

    When ``credentials['enable_request_metadata']`` is ``"enabled"`` and
    ``credentials['app_id']`` resolves to a non-empty string, the result
    is ``RequestOptions(max_retries=0, additional_headers=...)`` carrying
    the Dify app_id and source markers. In every other case the result is
    ``RequestOptions(max_retries=0)`` with no additional headers, so the
    call site can use the same argument unconditionally.

    The function never raises. If anything goes wrong while building the
    options, it falls back to ``RequestOptions(max_retries=0)`` so the
    user's request still proceeds.
    """
    try:
        if credentials.get("enable_request_metadata") != _ENABLED:
            return RequestOptions(max_retries=0)
        app_id = credentials.get("app_id")
        if not app_id:
            return RequestOptions(max_retries=0)
        return RequestOptions(
            max_retries=0,
            additional_headers={
                _APP_ID_HEADER: str(app_id),
                _SOURCE_HEADER: _SOURCE_VALUE,
            },
        )
    except Exception:  # noqa: BLE001 - telemetry must never break the user request
        # Never block the user's request on metadata wiring.
        return RequestOptions(max_retries=0)


__all__ = ["build_cohere_request_options"]
