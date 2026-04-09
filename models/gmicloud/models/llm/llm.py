import logging
from collections.abc import Generator
from typing import Optional, Union
from yarl import URL

from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities import I18nObject
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    ModelType,
)
from dify_plugin.entities.model.llm import (
    LLMResult,
    LLMMode,
)
from dify_plugin.entities.model.message import (
    PromptMessage,
    PromptMessageTool,
)

logger = logging.getLogger(__name__)


class GmicloudLargeLanguageModel(OAICompatLargeLanguageModel):
    """
    Model class for gmicloud large language model.
    """

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
        """
        Invoke large language model

        :param model: model name
        :param credentials: model credentials
        :param prompt_messages: prompt messages
        :param model_parameters: model parameters
        :param tools: tools for tool calling
        :param stop: stop words
        :param stream: is stream response
        :param user: unique user id
        :return: full response or stream response chunk generator result
        """
        self._add_custom_parameters(credentials)
        return super()._invoke(model, credentials, prompt_messages, model_parameters, tools, stop, stream)
   
    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        """
        Get number of tokens for given prompt messages

        :param model: model name
        :param credentials: model credentials
        :param prompt_messages: prompt messages
        :param tools: tools for tool calling
        :return:
        """
        return 0

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        self._add_custom_parameters(credentials)
        super().validate_credentials(model, credentials)

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> AIModelEntity:
        """
        If your model supports fine-tuning, this method returns the schema of the base model
        but renamed to the fine-tuned model name.

        :param model: model name
        :param credentials: credentials

        :return: model schema
        """
        entity = AIModelEntity(
            model=model,
            label=I18nObject(zh_Hans=model, en_US=model),
            model_type=ModelType.LLM,
            features=[],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={},
            parameter_rules=[],
        )

        return entity

    @staticmethod
    def _add_custom_parameters(credentials) -> None:
        # Get base URL and normalize it
        endpoint_url = credentials.get("endpoint_url", "https://api.gmi-serving.com")
        endpoint_url = str(URL(endpoint_url)).rstrip("/")
        
        # Ensure endpoint URL includes /v1
        if "/v1" not in endpoint_url:
            endpoint_url = endpoint_url + "/v1"
        
        # Set the endpoint URL with /v1 included
        credentials["endpoint_url"] = endpoint_url
        credentials["mode"] = LLMMode.CHAT.value
        credentials["function_calling_type"] = "tool_call"
        credentials["stream_function_calling"] = "support"
        
        # Map gmicloud_api_key to api_key for OAICompatLargeLanguageModel
        # The OAI compat layer expects "api_key"
        if "gmicloud_api_key" in credentials and "api_key" not in credentials:
            credentials["api_key"] = credentials["gmicloud_api_key"]