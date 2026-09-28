from collections.abc import Generator
from typing import Optional, Union

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool


DEFAULT_ENDPOINT = "https://global.api-route.com/v1"


class APIRouteLargeLanguageModel(OAICompatLargeLanguageModel):
    @staticmethod
    def _credentials_with_defaults(credentials: dict) -> dict:
        prepared = dict(credentials)
        prepared["endpoint_url"] = prepared.get("endpoint_url") or DEFAULT_ENDPOINT
        prepared["mode"] = "chat"
        prepared.setdefault("function_calling_type", "tool_call")
        return prepared

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
        return super()._invoke(
            model,
            self._credentials_with_defaults(credentials),
            prompt_messages,
            model_parameters,
            tools,
            stop,
            stream,
            user,
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        return super().validate_credentials(
            model, self._credentials_with_defaults(credentials)
        )

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        return super().get_customizable_model_schema(
            model, self._credentials_with_defaults(credentials)
        )
