from typing import Optional, Union, Generator, Mapping

from dify_plugin.entities.model.llm import LLMResult, LLMMode
from dify_plugin.entities.model.message import PromptMessage, PromptMessageTool
from dify_plugin.interfaces.model.openai_compatible.llm import (
    OAICompatLargeLanguageModel,
)


class NetmindLargeLanguageModel(OAICompatLargeLanguageModel):
    def _update_endpoint_url(self, credentials: dict) -> dict:
        credentials["endpoint_url"] = "https://api.netmind.ai/inference-api/openai/v1"
        return credentials

    def validate_credentials(self, model: str, credentials: dict) -> None:
        cred_with_endpoint = self._update_endpoint_url(credentials=credentials)
        return super().validate_credentials(model, cred_with_endpoint)

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
        print(model_parameters)
        print(prompt_messages)
        print(credentials)
        cred_with_endpoint = self._update_endpoint_url(credentials=credentials)
        return super()._invoke(model, cred_with_endpoint, prompt_messages, model_parameters, tools, stop, stream, user)

    def _generate(
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
        cred_with_endpoint = self._update_endpoint_url(credentials=credentials)
        return super()._generate(
            model, cred_with_endpoint, prompt_messages, model_parameters, tools, stop, stream, user
        )

    def get_num_tokens(
            self,
            model: str,
            credentials: dict,
            prompt_messages: list[PromptMessage],
            tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        cred_with_endpoint = self._update_endpoint_url(credentials=credentials)
        return super().get_num_tokens(model, cred_with_endpoint, prompt_messages, tools)
