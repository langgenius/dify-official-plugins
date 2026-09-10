import logging
import re
import uuid
from typing import Generator, Optional, Union

from dify_plugin import OAICompatLargeLanguageModel
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

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT_URL = "https://opencode.ai/zen/go/v1"
DEFAULT_USER_AGENT = "dify-opencode-go-plugin/0.1.0"

# One identity per plugin process so different Dify installs never collide
# even when they share short end-user ids like "est-user" or "20162097".
_CLIENT_ID = uuid.uuid4().hex
_ANON_SESSION = uuid.uuid4().hex[:16]


class OpenCodeGoLargeLanguageModel(OAICompatLargeLanguageModel):
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
            ],
        )

    @classmethod
    def _build_session_id(cls, user: Optional[str], credentials: dict) -> str:
        """Build a collision-resistant, per-conversation-stable session id.

        OpenCode Go asks clients to send a stable session id for routing /
        prompt-cache affinity. Bare Dify user ids are often short
        (est-user / 20162097) and can collide across workspaces, so we
        namespace with a per-process client id.
        """
        explicit = str(credentials.get("session_id") or "").strip()
        if explicit:
            return explicit

        raw = (user or "").strip()
        user_part = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-._")[:32]
        if len(user_part) < 4:
            user_part = f"anon-{_ANON_SESSION}"

        # stable for this process + this Dify user; unique across installs
        return f"dify-opencode-go/{_CLIENT_ID[:16]}/{user_part}"

    @classmethod
    def _add_custom_parameters(cls, credentials: dict, user: Optional[str]) -> None:
        credentials["mode"] = "chat"
        if not credentials.get("endpoint_url"):
            credentials["endpoint_url"] = DEFAULT_ENDPOINT_URL
        credentials["function_calling_type"] = (
            credentials.get("function_calling_type") or "tool_call"
        )

        headers = dict(credentials.get("extra_headers") or {})
        # OpenCode Go requires a non-generic User-Agent.
        headers["User-Agent"] = (
            credentials.get("user_agent") or DEFAULT_USER_AGENT
        )
        headers["x-opencode-session"] = cls._build_session_id(user, credentials)
        credentials["extra_headers"] = headers
