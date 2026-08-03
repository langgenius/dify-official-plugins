from collections.abc import Generator
from typing import Optional, Union

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import AIModelEntity, ModelFeature
from dify_plugin.entities.model.llm import LLMResult
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool

DEFAULT_ENDPOINT_URL = "https://api.trustedrouter.com/v1"


class TrustedRouterLargeLanguageModel(OAICompatLargeLanguageModel):
    def _update_credential(self, model: str, credentials: dict):
        credentials["endpoint_url"] = DEFAULT_ENDPOINT_URL
        credentials["mode"] = self.get_model_mode(model).value
        credentials["openai_api_key"] = credentials["api_key"]
        schema = self.get_model_schema(model, credentials)
        if schema and {
            ModelFeature.TOOL_CALL,
            ModelFeature.MULTI_TOOL_CALL,
        }.intersection(schema.features or []):
            credentials["function_calling_type"] = "tool_call"

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
        self._update_credential(model, credentials)
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
        self._update_credential(model, credentials)
        super().validate_credentials(model, credentials)

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> AIModelEntity:
        return super().get_customizable_model_schema(model, credentials)

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        self._update_credential(model, credentials)
        return super().get_num_tokens(model, credentials, prompt_messages, tools)
