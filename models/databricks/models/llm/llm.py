import logging
from collections.abc import Generator
from typing import Optional, Union

from openai import OpenAI, Stream
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from dify_plugin import LargeLanguageModel
from dify_plugin.entities import I18nObject
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
)
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    ModelType,
)
from dify_plugin.entities.model.llm import (
    LLMResult,
)
from dify_plugin.entities.model.message import (
    PromptMessage,
    PromptMessageTool,
    UserPromptMessage,
    SystemPromptMessage,
    AssistantPromptMessage,
    ToolPromptMessage,
)

logger = logging.getLogger(__name__)


class DatabricksLargeLanguageModel(LargeLanguageModel):
    """
    Model class for databricks large language model.
    """

    def _create_client(self, credentials: dict) -> OpenAI:
        """
        Create OpenAI client configured for Databricks

        :param credentials: credentials dict with databricks_token and databricks_host
        :return: OpenAI client instance
        """
        return OpenAI(
            api_key=credentials.get("databricks_token"),
            base_url=f"{credentials.get('databricks_host').rstrip('/')}/serving-endpoints"
        )

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
        pass
   
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
        Validate model credentials by making a minimal API call

        :param model: model name
        :param credentials: model credentials containing databricks_token and databricks_host
        :return:
        """
        try:
            # Create OpenAI client configured for Databricks
            client = self._create_client(credentials)

            # Make a minimal API call to validate credentials
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": "ping"}
                ],
                max_tokens=5,
                temperature=0
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _convert_prompt_messages(self, prompt_messages: list[PromptMessage]) -> list[dict]:
        """
        Convert Dify prompt messages to OpenAI format

        :param prompt_messages: Dify prompt messages
        :return: OpenAI formatted messages
        """
        messages = []
        for message in prompt_messages:
            if isinstance(message, SystemPromptMessage):
                messages.append({"role": "system", "content": message.content})
            elif isinstance(message, UserPromptMessage):
                messages.append({"role": "user", "content": message.content})
            elif isinstance(message, AssistantPromptMessage):
                msg_dict = {"role": "assistant", "content": message.content}
                if message.tool_calls:
                    msg_dict["tool_calls"] = [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                        for tool_call in message.tool_calls
                    ]
                messages.append(msg_dict)
            elif isinstance(message, ToolPromptMessage):
                messages.append({
                    "role": "tool",
                    "tool_call_id": message.tool_call_id,
                    "content": message.content,
                })
        return messages

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
