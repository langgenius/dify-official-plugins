import logging
from collections.abc import Generator
from typing import Mapping

from dify_plugin.entities.model import (
    AIModelEntity,
    I18nObject,
    ParameterRule,
    ParameterType,
)
from dify_plugin.entities.model.llm import LLMMode
from dify_plugin.entities.model.message import PromptMessage
from dify_plugin.interfaces.model.openai_compatible.llm import OAICompatLargeLanguageModel

logger = logging.getLogger(__name__)

DEFAULT_AIMLAPI_ENDPOINT = "https://api.aimlapi.com/v1"
VALIDATION_PROBE_MODEL = "gpt-4o-mini"


class AIMLAPILargeLanguageModel(OAICompatLargeLanguageModel):
    """LLM implementation for the AI/ML API OpenAI-compatible gateway."""

    def _resolve_endpoint_url(self, credentials: Mapping) -> str:
        endpoint = credentials.get("endpoint_url")
        if isinstance(endpoint, str) and endpoint.strip():
            return endpoint.strip()
        return DEFAULT_AIMLAPI_ENDPOINT

    def _resolve_api_key(self, credentials: Mapping) -> str:
        api_key = credentials.get("aimlapi_api_key") or credentials.get("api_key")
        if not api_key:
            raise ValueError("AI/ML API key is required (aimlapi_api_key).")
        return api_key

    def _invoke(
        self,
        model: str,
        credentials: Mapping,
        prompt_messages: list[PromptMessage],
        model_parameters: Mapping,
        tools: list | None = None,
        stop: list[str] | None = None,
        stream: bool = True,
        user: str | None = None,
    ) -> Generator:
        credentials = dict(credentials)
        credentials["endpoint_url"] = self._resolve_endpoint_url(credentials)
        credentials["api_key"] = self._resolve_api_key(credentials)
        yield from super()._invoke(
            model=model,
            credentials=credentials,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user,
        )

    def validate_credentials(self, model: str, credentials: Mapping) -> None:
        """Probe the AI/ML API endpoint with a minimal chat completion."""
        probe_model = model or VALIDATION_PROBE_MODEL
        merged = dict(credentials)
        merged["endpoint_url"] = self._resolve_endpoint_url(merged)
        merged["api_key"] = self._resolve_api_key(merged)
        super().validate_credentials(probe_model, merged)

    def get_customizable_model_schema(self, model: str, credentials: Mapping) -> AIModelEntity:
        entity = super().get_customizable_model_schema(model, credentials)
        entity.parameter_rules += [
            ParameterRule(
                name="temperature",
                label=I18nObject(en_US="Temperature", zh_Hans="温度"),
                type=ParameterType.FLOAT,
                default=0.7,
                min=0.0,
                max=2.0,
                precision=1,
            ),
            ParameterRule(
                name="top_p",
                label=I18nObject(en_US="Top P", zh_Hans="Top P"),
                type=ParameterType.FLOAT,
                default=1.0,
                min=0.0,
                max=1.0,
                precision=1,
            ),
        ]
        return entity

    def get_model_mode(self, model: str, credentials: Mapping) -> LLMMode:
        mode = credentials.get("mode")
        if mode == "completion":
            return LLMMode.COMPLETION
        return LLMMode.CHAT