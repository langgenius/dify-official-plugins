"""Map upstream HTTP/stream errors to messages ordinary Dify users can read.

Upstream gateways return raw JSON (GoUsageLimitError, Param Incorrect, ...).
Dify surfaces the exception text verbatim, so end users see machine dumps.
This module rewrites known failure shapes into short actionable Chinese text
and keeps a one-line technical detail for support.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

# Matches "API request failed with status code 429: {body}" from OAICompat.
_STATUS_BODY_RE = re.compile(
    r"API request failed with status code (\d{3})[:\s]+(.*)$",
    re.DOTALL,
)


def _parse_body(body_text: str) -> tuple[dict[str, Any], str]:
    """Return (parsed_json_or_empty, lowercased_text)."""
    text = body_text or ""
    lowered = text.lower()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}, lowered
    if isinstance(data, dict):
        return data, lowered
    return {}, lowered


def _dig(data: dict[str, Any], *keys: str) -> Optional[str]:
    """Return the first non-empty string found under any of the key paths."""
    for key in keys:
        cur: Any = data
        for part in key.split("."):
            if not isinstance(cur, dict):
                cur = None
                break
            cur = cur.get(part)
        if isinstance(cur, str) and cur.strip():
            return cur.strip()
        if isinstance(cur, (int, float)) and not isinstance(cur, bool):
            return str(cur)
    return None


def _limit_label(data: dict[str, Any], lowered: str) -> str:
    """Human label for a usage window, e.g. "5 小时"."""
    raw = _dig(data, "metadata.limitName", "limitName", "error.limitName")
    if not raw:
        m = re.search(r"limitname\"?\s*[:=]\s*\"?([a-z0-9 _-]+)", lowered)
        raw = m.group(1).strip() if m else None
    if not raw:
        return "当前"
    mapping = {
        "5 hour": "5 小时",
        "5 hours": "5 小时",
        "hour": "1 小时",
        "day": "1 天",
        "daily": "每日",
        "week": "每周",
        "month": "每月",
        "year": "每年",
        "minute": "1 分钟",
    }
    return mapping.get(raw.lower(), raw)


def _detail(status: Optional[int], data: dict[str, Any], raw: str) -> str:
    """Short technical tail: prefer structured fields over the raw dump."""
    label = _dig(data, "error.type", "type") or _dig(data, "error.message", "message")
    if not label:
        label = " ".join((raw or "").split())[:60]
    label = (label or "").strip()
    if status is not None and label:
        return f"（详情：HTTP {status} · {label}）"
    if status is not None:
        return f"（详情：HTTP {status}）"
    if label:
        return f"（详情：{label}）"
    return ""


def map_upstream_error(
    status: Optional[int],
    body_text: str,
    *,
    protocol: str = "模型",
) -> Exception:
    """Translate an upstream HTTP/stream failure into a typed Invoke* error.

    The exception message is end-user facing; `_detail()` keeps a short
    technical tail so support can still identify the original payload.
    """
    data, lowered = _parse_body(body_text)
    err = data.get("error") if isinstance(data.get("error"), dict) else {}
    err_type = (_dig(data, "error.type", "type") or "").lower()
    err_msg = (_dig(data, "error.message", "message") or "").lower()
    param = _dig(data, "error.param", "param")
    detail = _detail(status, data, body_text)

    # --- Plan / quota exhausted (GoUsageLimitError and friends) ---
    quota_hit = (
        "gousagelimiterror" in lowered
        or "usage limit exceeded" in lowered
        or "usage_limit" in lowered
        or "quota" in lowered and "exceed" in lowered
        or err_type in {"gousagelimiterror", "usage_limit_error", "quota_exceeded"}
    )
    if quota_hit:
        window = _limit_label(data, lowered)
        return InvokeRateLimitError(
            f"模型调用失败：套餐用量已达上限（{window}额度）。"
            f"请等待额度重置后再试，或升级套餐后继续使用。{detail}"
        )

    # --- Region policy ---
    if "unsupported_country_region_territory" in lowered or (
        "region" in lowered and "not supported" in lowered
    ):
        return InvokeAuthorizationError(
            f"模型调用失败：当前地区不受支持，请更换网络环境后重试。{detail}"
        )

    # --- Auth ---
    if status in (401, 403) or err_type in {
        "authentication_error",
        "permission_error",
        "unauthorized",
        "forbidden",
    }:
        return InvokeAuthorizationError(
            f"模型调用失败：API Key 无效或无访问权限，"
            f"请检查模型配置中的 API Key 是否正确、是否已过期。{detail}"
        )

    # --- Parameter rejected (e.g. top_p out of range) ---
    if status == 400 and (param or "param incorrect" in lowered or "must be within" in lowered):
        hint = param or err_msg or "请求参数不符合上游要求"
        return InvokeBadRequestError(
            f"模型调用失败：请求参数不合法（{hint}）。"
            f"请在模型参数中调整后重试，例如 Top P 需在 0.01～1.0 之间。{detail}"
        )

    # --- Generic rate limit ---
    if status == 429 or err_type in {"rate_limit_error", "ratelimiterror"}:
        return InvokeRateLimitError(
            f"模型调用失败：请求过于频繁，已被限流，请稍后重试。{detail}"
        )

    # --- Client-side bad request ---
    if status == 400 or status == 404 or status == 422:
        return InvokeBadRequestError(
            f"模型调用失败：请求参数或模型名称不正确，请检查模型配置后重试。{detail}"
        )

    # --- Upstream 5xx / busy ---
    if status is not None and status >= 500:
        return InvokeServerUnavailableError(
            f"模型服务暂时不可用，请稍后重试；若持续出现请联系管理员。{detail}"
        )

    if "timeout" in lowered or "timed out" in lowered:
        return InvokeConnectionError(
            f"模型调用失败：连接超时，请检查网络后重试。{detail}"
        )

    if "connection" in lowered and (
        "refused" in lowered or "reset" in lowered or "error" in lowered
    ):
        return InvokeConnectionError(
            f"模型调用失败：无法连接模型服务，请检查网络或服务地址后重试。{detail}"
        )

    return InvokeError(
        f"模型调用失败，请稍后重试；若持续出现请联系管理员。{detail}"
    )


def map_http_error(status: int, body_text: str, *, protocol: str = "模型") -> Exception:
    """HTTP status + body → typed user-facing exception."""
    return map_upstream_error(status, body_text, protocol=protocol)


def rewrite_invoke_error(exc: BaseException) -> Exception:
    """Rewrite a raw InvokeError (OAICompat chat path) into a friendly one.

    OAICompat raises ``InvokeError("API request failed with status code N: body")``.
    Parse that shape and re-map; anything else is returned unchanged unless it
    still matches a known failure keyword.
    """
    if isinstance(exc, InvokeConnectionError | InvokeServerUnavailableError | InvokeRateLimitError | InvokeAuthorizationError | InvokeBadRequestError):
        # Already typed — still re-map if the text is a raw upstream dump.
        text = str(exc)
        if "api request failed" not in text.lower() and "gousagelimit" not in text.lower():
            return exc  # type: ignore[return-value]

    text = str(exc)
    m = _STATUS_BODY_RE.search(text)
    if m:
        return map_upstream_error(int(m.group(1)), m.group(2))
    return map_upstream_error(None, text)


def wrap_stream_error(message: str, *, protocol: str = "模型") -> Exception:
    """Map a mid-stream error event payload to a friendly exception."""
    return map_upstream_error(None, message, protocol=protocol)
