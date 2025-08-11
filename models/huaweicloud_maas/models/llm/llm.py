from collections.abc import Generator
from typing import Optional, Union
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


class HuaweiCloudMaasLargeLanguageModel(OAICompatLargeLanguageModel):
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
        self._add_custom_parameters(credentials)
        self._add_function_call(model, credentials)
        return super()._invoke(
            model, credentials, prompt_messages, model_parameters, tools, stop, stream
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        self._add_custom_parameters(credentials)
        super().validate_credentials(model, credentials)

    @classmethod
    def _add_custom_parameters(cls, credentials: dict) -> None:
        credentials["mode"] = "chat"
        credentials["endpoint_url"] = str(credentials.get("endpoint_url", "https://api.modelarts-maas.com/v1"))
    
    def _add_function_call(self, model: str, credentials: dict) -> None:
        model_schema = self.get_model_schema(model, credentials)
        if model_schema and {ModelFeature.TOOL_CALL, ModelFeature.MULTI_TOOL_CALL}.intersection(
            model_schema.features or []
        ):
            credentials["function_calling_type"] = "tool_call"
    
    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        entity = super().get_customizable_model_schema(model, credentials)

        return entity
