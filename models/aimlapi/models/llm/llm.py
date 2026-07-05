import logging
from collections.abc import Generator
from typing import Mapping

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

    def _inject_credentials(self, credentials: Mapping) -> dict:
        merged = dict(credentials)
        merged["endpoint_url"] = self._resolve_endpoint_url(merged)
        merged["api_key"] = self._resolve_api_key(merged)
        return merged

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
        yield from super()._invoke(
            model=model,
            credentials=self._inject_credentials(credentials),
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user,
        )

    def validate_credentials(self, model: str, credentials: Mapping) -> None:
        """Probe the AI/ML API endpoint with a minimal chat completion."""
        super().validate_credentials(model or VALIDATION_PROBE_MODEL, self._inject_credentials(credentials))

    def get_model_mode(self, model: str, credentials: Mapping) -> LLMMode:
        mode = credentials.get("mode")
        if mode == "completion":
            return LLMMode.COMPLETION
        return LLMMode.CHAT