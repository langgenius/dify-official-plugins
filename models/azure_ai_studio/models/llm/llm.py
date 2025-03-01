import logging
from collections.abc import Generator, Sequence
from typing import Any, Optional, Union
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import (
    StreamingChatCompletionsUpdate,
    SystemMessage,
    UserMessage,
)
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import (
    ClientAuthenticationError,
    DecodeError,
    DeserializationError,
    HttpResponseError,
    ResourceExistsError,
    ResourceModifiedError,
    ResourceNotFoundError,
    ResourceNotModifiedError,
    SerializationError,
    ServiceRequestError,
    ServiceResponseError,
)
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    I18nObject,
    ModelPropertyKey,
    ModelType,
    ParameterRule,
    ParameterType,
)
from dify_plugin.entities.model.llm import (
    LLMMode,
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
)
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeServerUnavailableError,
)
from dify_plugin.interfaces.model.large_language_model import LargeLanguageModel

logger = logging.getLogger(__name__)


class AzureAIStudioLargeLanguageModel(LargeLanguageModel):
    """
    Model class for Azure AI Studio large language model.
    """

    client: Any = None
    from azure.ai.inference.models import StreamingChatCompletionsUpdate

    def _invoke(
        self,
        model: str,
        credentials: dict,
        prompt_messages: Sequence[PromptMessage],
        model_parameters: dict,
        tools: Optional[Sequence[PromptMessageTool]] = None,
        stop: Optional[Sequence[str]] = None,
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
        if not self.client:
            endpoint = str(credentials.get("endpoint"))
            api_key = str(credentials.get("api_key"))
            self.client = ChatCompletionsClient(
                endpoint=endpoint, credential=AzureKeyCredential(api_key)
            )
        messages = [
            {"role": msg.role.value, "content": msg.content} for msg in prompt_messages
        ]
        payload = {
            "messages": messages,
            "max_tokens": model_parameters.get("max_tokens", 4096),
            "temperature": model_parameters.get("temperature", 0),
            "top_p": model_parameters.get("top_p", 1),
            "stream": stream,
            "model": model,
        }
        if stop:
            payload["stop"] = stop
        if tools:
            payload["tools"] = [tool.model_dump() for tool in tools]
        try:
            response = self.client.complete(**payload)
            if stream:
                return self._handle_stream_response(response, model, prompt_messages)
            else:
                return self._handle_non_stream_response(
                    response, model, prompt_messages, credentials
                )
        except Exception as e:
            raise self._transform_invoke_error(e)

    def _handle_stream_response(
        self, response, model: str, prompt_messages: Sequence[PromptMessage]
    ) -> Generator:
        for chunk in response:
            if isinstance(chunk, StreamingChatCompletionsUpdate):
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield LLMResultChunk(
                            model=model,
                            prompt_messages=list(prompt_messages),
                            delta=LLMResultChunkDelta(
                                index=0,
                                message=AssistantPromptMessage(
                                    content=delta.content, tool_calls=[]
                                ),
                            ),
                        )

    def _handle_non_stream_response(
        self,
        response,
        model: str,
        prompt_messages: Sequence[PromptMessage],
        credentials: dict,
    ) -> LLMResult:
        assistant_text = response.choices[0].message.content
        assistant_prompt_message = AssistantPromptMessage(content=assistant_text)
        usage = self._calc_response_usage(
            model,
            credentials,
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
        )
        result = LLMResult(
            model=model,
            prompt_messages=list(prompt_messages),
            message=assistant_prompt_message,
            usage=usage,
        )
        if hasattr(response, "system_fingerprint"):
            result.system_fingerprint = response.system_fingerprint
        return result

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
        try:
            endpoint = str(credentials.get("endpoint"))
            api_key = str(credentials.get("api_key"))
            client = ChatCompletionsClient(
                endpoint=endpoint, credential=AzureKeyCredential(api_key)
            )
            client.complete(
                messages=[
                    SystemMessage(content="I say 'ping', you say 'pong'"),
                    UserMessage(content="ping"),
                ],
                model=model,
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        The key is the error type thrown to the caller
        The value is the error type thrown by the model,
        which needs to be converted into a unified error type for the caller.

        :return: Invoke error mapping
        """
        return {
            InvokeConnectionError: [ServiceRequestError],
            InvokeServerUnavailableError: [ServiceResponseError],
            InvokeAuthorizationError: [ClientAuthenticationError],
            InvokeBadRequestError: [
                HttpResponseError,
                DecodeError,
                ResourceExistsError,
                ResourceNotFoundError,
                ResourceModifiedError,
                ResourceNotModifiedError,
                SerializationError,
                DeserializationError,
            ],
        }

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        """
        Used to define customizable model schema
        """
        rules = [
            ParameterRule(
                name="temperature",
                type=ParameterType.FLOAT,
                use_template="temperature",
                label=I18nObject(zh_Hans="温度", en_US="Temperature"),
            ),
            ParameterRule(
                name="top_p",
                type=ParameterType.FLOAT,
                use_template="top_p",
                label=I18nObject(zh_Hans="Top P", en_US="Top P"),
            ),
            ParameterRule(
                name="max_tokens",
                type=ParameterType.INT,
                use_template="max_tokens",
                min=1,
                default=512,
                label=I18nObject(zh_Hans="最大生成长度", en_US="Max Tokens"),
            ),
        ]
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_US=model),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.LLM,
            features=[],
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(credentials.get("context_size", "4096")),
                ModelPropertyKey.MODE: credentials.get("mode", LLMMode.CHAT),
            },
            parameter_rules=rules,
        )
        return entity
