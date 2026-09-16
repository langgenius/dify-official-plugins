import json
import logging
import re
import uuid
from typing import Any, Generator, Optional, Union

from dify_plugin import OAICompatLargeLanguageModel, get_current_session
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    I18nObject,
    ModelFeature,
    ModelPropertyKey,
    ModelType,
    ParameterRule,
    ParameterType,
)
from dify_plugin.entities.model.llm import LLMMode, LLMResult
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool
from dify_plugin.errors.model import InvokeError

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT_URL = "https://opencode.ai/zen/go/v1"
DEFAULT_USER_AGENT = "dify-opencode-go-plugin/0.1.0"
# Internal only — consumed by the plugin, never sent upstream.
_RUN_ID_HEADER = "x-dify-run-id"


def _extra_headers_rule() -> ParameterRule:
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


class OpenCodeGoLargeLanguageModel(OAICompatLargeLanguageModel):
    @staticmethod
    def _inject_extra_headers_rule(entity: AIModelEntity) -> AIModelEntity:
        if not any(rule.name == "extra_headers" for rule in entity.parameter_rules):
            entity.parameter_rules.append(_extra_headers_rule())
        return entity

    def predefined_models(self) -> list[AIModelEntity]:
        return [self._inject_extra_headers_rule(m) for m in super().predefined_models()]

    def get_model_schema(
        self, model: str, credentials: Optional[dict] = None
    ) -> Optional[AIModelEntity]:
        schema = super().get_model_schema(model, credentials)
        return self._inject_extra_headers_rule(schema) if schema else None

    def _invoke(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: Optional[list[PromptMessageTool]] = None,
        stop: Optional[list[str]] = None,
        stream: bool = True,
        user: Optional[str] = None,
    ) -> Union[LLMResult, Generator]:
        self._apply_extra_headers(credentials, model_parameters)
        self._add_custom_parameters(credentials, user)
        return super()._invoke(
            model,
            credentials,
            prompt_messages,
            model_parameters,
            tools,
            stop,
            stream,
            user,
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials, user=None)
        super().validate_credentials(model, credentials)

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        self._add_custom_parameters(credentials, user=None)
        features: list[ModelFeature] = []
        if credentials.get("function_calling_type", "tool_call") == "tool_call":
            features.extend(
                [
                    ModelFeature.TOOL_CALL,
                    ModelFeature.MULTI_TOOL_CALL,
                    ModelFeature.STREAM_TOOL_CALL,
                ]
            )
        if credentials.get("vision_support", "false") == "true":
            features.append(ModelFeature.VISION)

        return AIModelEntity(
            model=model,
            label=I18nObject(en_us=model, zh_hans=model),
            model_type=ModelType.LLM,
            features=features,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(
                    credentials.get("context_size", 262144)
                ),
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    use_template="temperature",
                    label=I18nObject(en_us="Temperature", zh_hans="温度"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="top_p",
                    use_template="top_p",
                    label=I18nObject(en_us="Top P", zh_hans="Top P"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="max_tokens",
                    use_template="max_tokens",
                    default=4096,
                    min=1,
                    max=int(credentials.get("max_tokens", 32768)),
                    label=I18nObject(en_us="Max Tokens", zh_hans="最大 Token"),
                    type=ParameterType.INT,
                ),
                _extra_headers_rule(),
            ],
        )

    @staticmethod
    def _parse_extra_headers(raw: Any) -> dict[str, str]:
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

    @classmethod
    def _apply_extra_headers(cls, credentials: dict, model_parameters: dict) -> None:
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
            k: v for k, v in cls._parse_extra_headers(raw_extra_headers).items() if str(v).strip()
        }
        credentials["_opencode_node_extra_headers"] = True

        if not parsed_headers:
            return

        existing_headers = credentials.get("extra_headers")
        if existing_headers:
            merged_headers = {
                **cls._parse_extra_headers(existing_headers),
                **parsed_headers,
            }
        else:
            merged_headers = parsed_headers
        credentials["extra_headers"] = merged_headers

    @classmethod
    def _current_conversation_id(cls) -> Optional[str]:
        try:
            session = get_current_session()
        except Exception:
            return None
        if session is None:
            return None
        conv = (session.conversation_id or "").strip()
        return conv or None

    @classmethod
    def _build_session_id(cls, user: Optional[str], credentials: dict) -> str:
        """OpenCode only needs a stable per-conversation id — pass the unique
        Dify id as-is (docs: x-opencode-session for routing / prompt cache).
        """
        explicit = str(credentials.get("session_id") or "").strip()
        if explicit:
            return explicit

        conversation = re.sub(
            r"[^A-Za-z0-9._-]+", "-", cls._current_conversation_id() or ""
        ).strip("-._")[:64]
        if len(conversation) >= 4:
            return conversation

        # extra_headers present but conversation empty/unresolved — isolate per invoke.
        if credentials.get("_opencode_node_extra_headers"):
            return uuid.uuid4().hex

        # Agent / unchecked extra_headers: still isolate per invoke. Never sticky
        # on Dify user (that collapsed every run onto one OpenCode session).
        rpc_session = cls._current_rpc_session_id()
        if rpc_session:
            return rpc_session[:64]

        return uuid.uuid4().hex

    @classmethod
    def _current_rpc_session_id(cls) -> Optional[str]:
        try:
            session = get_current_session()
        except Exception:
            return None
        if session is None:
            return None
        return (getattr(session, "session_id", None) or "").strip() or None

    @staticmethod
    def _is_resolved_id(value: str) -> bool:
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

    @classmethod
    def _add_custom_parameters(cls, credentials: dict, user: Optional[str]) -> None:
        credentials["mode"] = "chat"
        if not credentials.get("endpoint_url"):
            credentials["endpoint_url"] = DEFAULT_ENDPOINT_URL
        credentials["function_calling_type"] = (
            credentials.get("function_calling_type") or "tool_call"
        )

        headers = cls._parse_extra_headers(credentials.get("extra_headers"))

        # Drop auto sessions that Dify may have persisted back into credentials
        # after a previous invoke/schema call — never treat them as configured.
        existing = str(headers.get("x-opencode-session") or "")
        if existing.startswith("dify-opencode-go/") or not cls._is_resolved_id(
            existing
        ):
            if "x-opencode-session" in headers:
                del headers["x-opencode-session"]
            existing = ""

        # Prefer conversation; if empty (Workflow), fall back to run id from
        # the default extra_headers payload. Never send the helper header out.
        run_id = str(headers.pop(_RUN_ID_HEADER, "") or "").strip()
        if not cls._is_resolved_id(run_id):
            run_id = ""
        used_run_id = False
        if not existing and run_id:
            headers["x-opencode-session"] = run_id
            existing = run_id
            used_run_id = True

        if not any(k.lower() == "user-agent" for k in headers):
            headers["User-Agent"] = credentials.get("user_agent") or DEFAULT_USER_AGENT
        if "x-opencode-session" not in headers:
            headers["x-opencode-session"] = cls._build_session_id(user, credentials)
        credentials["extra_headers"] = headers

        try:
            sess = get_current_session()
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
