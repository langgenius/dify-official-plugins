"""Shared OpenCode Go session / User-Agent / extra_headers helpers.

Used by the chat (OAICompat), Anthropic Messages, and OpenAI Responses paths so
session isolation stays identical across protocols.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Optional

from dify_plugin.entities.model import I18nObject, ParameterRule, ParameterType
from dify_plugin.errors.model import InvokeError

logger = logging.getLogger(__name__)


def _get_current_session():
    """Prefer models.llm.llm.get_current_session so tests can patch it."""
    import sys

    for name in ("models.llm.llm", "llm"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "get_current_session"):
            return mod.get_current_session()
    from dify_plugin import get_current_session as _default

    return _default()

DEFAULT_ENDPOINT_URL = "https://opencode.ai/zen/go/v1"
DEFAULT_USER_AGENT = "dify-opencode-go-plugin/0.4.2"
# Internal only — consumed by the plugin, never sent upstream.
_RUN_ID_HEADER = "x-dify-run-id"
ANTHROPIC_VERSION = "2023-06-01"


def extra_headers_rule() -> ParameterRule:
    return ParameterRule(
        name="extra_headers",
        label=I18nObject(en_us="Extra Headers", zh_hans="额外请求头"),
        help=I18nObject(
            en_us=(
                "Recommended: enable this parameter and keep the default JSON. "
                "It auto-selects Chatflow conversation id vs Workflow run id "
                "for OpenCode routing / prompt cache. If left disabled, sessions "
                "are still isolated per invoke (may split one workflow run "
                "across multiple LLM nodes)."
            ),
            zh_hans=(
                "建议开启本参数并保留默认 JSON。"
                "会自动选择 Chatflow 会话 ID 或工作流运行 ID，"
                "用于 OpenCode 路由与 prompt cache。"
                "若不开启，仍会按次隔离会话，但同一次工作流内多个 LLM 节点可能各用各的 session。"
            ),
        ),
        type=ParameterType.STRING,
        required=True,
        default=(
            '{"x-opencode-session": "{{#sys.conversation_id#}}", '
            '"x-dify-run-id": "{{#sys.workflow_run_id#}}"}'
        ),
    )


def parse_extra_headers(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    if isinstance(raw, str):
        value = raw.strip()
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise InvokeError(
                "extra_headers must be a JSON object of header names to values"
            ) from exc
        if not isinstance(parsed, dict):
            raise InvokeError("extra_headers must be a JSON object")
        return {str(key): str(value) for key, value in parsed.items()}
    raise InvokeError("extra_headers must be a JSON object or JSON string")


def apply_extra_headers(credentials: dict, model_parameters: dict) -> None:
    """Merge LLM-node extra_headers (Dify-resolved) into credentials.

    Empty resolved values (e.g. conversation_id on Workflow) are dropped so
    session generation can fall back to a per-run id instead of a sticky user.
    """
    raw_extra_headers = model_parameters.pop("extra_headers", None)
    if raw_extra_headers is None or (
        isinstance(raw_extra_headers, str) and not raw_extra_headers.strip()
    ):
        credentials.pop("_opencode_node_extra_headers", None)
        return

    parsed_headers = {
        k: v
        for k, v in parse_extra_headers(raw_extra_headers).items()
        if str(v).strip()
    }
    credentials["_opencode_node_extra_headers"] = True

    if not parsed_headers:
        return

    existing_headers = credentials.get("extra_headers")
    if existing_headers:
        merged_headers = {**parse_extra_headers(existing_headers), **parsed_headers}
    else:
        merged_headers = parsed_headers
    credentials["extra_headers"] = merged_headers


def current_conversation_id() -> Optional[str]:
    try:
        session = _get_current_session()
    except Exception:
        return None
    if session is None:
        return None
    conv = (session.conversation_id or "").strip()
    return conv or None


def current_rpc_session_id() -> Optional[str]:
    try:
        session = _get_current_session()
    except Exception:
        return None
    if session is None:
        return None
    return (getattr(session, "session_id", None) or "").strip() or None


def is_resolved_id(value: str) -> bool:
    """True only for a real id — reject unresolved Dify templates.

    Dify sometimes injects the default extra_headers without resolving
    {{#sys.*#}} (e.g. {{#sys.conversation_id#}} or sys.conversation_id).
    Sending those as x-opencode-session makes every request share one
    garbage session in the OpenCode console.
    """
    v = (value or "").strip()
    if not v or len(v) > 128:
        return False
    lowered = v.lower()
    if "{{" in v or "}}" in v or "#sys." in lowered or "sys." in lowered:
        return False
    if lowered in {"none", "null", "undefined"}:
        return False
    return True


def build_session_id(user: Optional[str], credentials: dict) -> str:
    """OpenCode only needs a stable per-conversation id — pass the unique
    Dify id as-is (docs: x-opencode-session for routing / prompt cache).
    """
    explicit = str(credentials.get("session_id") or "").strip()
    if explicit:
        return explicit

    conversation = re.sub(
        r"[^A-Za-z0-9._-]+", "-", current_conversation_id() or ""
    ).strip("-._")[:64]
    if len(conversation) >= 4:
        return conversation

    # extra_headers present but conversation empty/unresolved — isolate per invoke.
    if credentials.get("_opencode_node_extra_headers"):
        return uuid.uuid4().hex

    # Agent / unchecked extra_headers: still isolate per invoke. Never sticky
    # on Dify user (that collapsed every run onto one OpenCode session).
    rpc_session = current_rpc_session_id()
    if rpc_session:
        return rpc_session[:64]

    return uuid.uuid4().hex


def add_custom_parameters(credentials: dict, user: Optional[str]) -> dict[str, str]:
    """Normalize credentials and return the header map to send upstream."""
    credentials["mode"] = "chat"
    if not credentials.get("endpoint_url"):
        credentials["endpoint_url"] = DEFAULT_ENDPOINT_URL
    credentials["function_calling_type"] = (
        credentials.get("function_calling_type") or "tool_call"
    )

    headers = parse_extra_headers(credentials.get("extra_headers"))

    # Drop auto sessions that Dify may have persisted back into credentials
    # after a previous invoke/schema call — never treat them as configured.
    existing = str(headers.get("x-opencode-session") or "")
    if existing.startswith("dify-opencode-go/") or not is_resolved_id(existing):
        if "x-opencode-session" in headers:
            del headers["x-opencode-session"]
        existing = ""

    # Prefer conversation; if empty (Workflow), fall back to run id from
    # the default extra_headers payload. Never send the helper header out.
    run_id = str(headers.pop(_RUN_ID_HEADER, "") or "").strip()
    if not is_resolved_id(run_id):
        run_id = ""
    used_run_id = False
    if not existing and run_id:
        headers["x-opencode-session"] = run_id
        existing = run_id
        used_run_id = True

    if not any(k.lower() == "user-agent" for k in headers):
        headers["User-Agent"] = credentials.get("user_agent") or DEFAULT_USER_AGENT
    if "x-opencode-session" not in headers:
        headers["x-opencode-session"] = build_session_id(user, credentials)
    credentials["extra_headers"] = headers

    try:
        sess = _get_current_session()
        conv = (getattr(sess, "conversation_id", None) or "") if sess else ""
        rpc = (getattr(sess, "session_id", None) or "") if sess else ""
    except Exception:
        conv, rpc = "", ""
    node_extra = bool(credentials.pop("_opencode_node_extra_headers", False))
    logger.info(
        "opencode-go session=%s used_run_id=%s node_extra_headers=%s conv=%s rpc=%s user=%s",
        headers.get("x-opencode-session"),
        used_run_id,
        node_extra,
        conv or "-",
        (rpc[:8] + "...") if rpc else "-",
        user,
    )
    return headers


# Predefined models that only work on Anthropic Messages / OpenAI Responses.
# union-alpha is no longer in the Go catalog but custom ids may still use these routes.
ANTHROPIC_MODELS = frozenset({"union-alpha", "minimax-m2.7"})
RESPONSES_MODELS = frozenset(
    {
        "grok-4.7",
        "grok-4.6",
        "gpt-6-luna",
        "gpt-5.6-luna",
        "muse-spark-1.3-contributor",
        "muse-spark-1.2-contributor",
    }
)


def resolve_protocol(model: str, credentials: dict) -> str:
    """Return 'chat' | 'anthropic' | 'responses'."""
    explicit = str(credentials.get("api_protocol") or "").strip().lower()
    if explicit in {"chat", "anthropic", "responses"}:
        return explicit
    if model in ANTHROPIC_MODELS:
        return "anthropic"
    if model in RESPONSES_MODELS:
        return "responses"
    return "chat"


def join_endpoint_url(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def public_headers_for_protocol(
    headers: dict[str, str], api_key: str, protocol: str
) -> dict[str, str]:
    """Clone shared headers and attach protocol-specific auth.

    Anthropic Messages requires x-api-key and must NOT send Authorization Bearer
    (OpenCode returns 401 when both are present / wrong scheme).
    """
    out = {k: v for k, v in headers.items()}
    if protocol == "anthropic":
        out.pop("Authorization", None)
        out.pop("authorization", None)
        out["x-api-key"] = api_key
        out.setdefault("anthropic-version", ANTHROPIC_VERSION)
    else:
        out.pop("x-api-key", None)
        out.pop("anthropic-version", None)
        out["Authorization"] = f"Bearer {api_key}"
    out.setdefault("Content-Type", "application/json")
    out.setdefault("Accept", "application/json")
    return out
