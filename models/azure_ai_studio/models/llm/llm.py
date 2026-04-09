import logging
from collections.abc import Generator, Sequence
from typing import Any, Optional, Union

from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import (
    StreamingChatCompletionsUpdate,
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
    ModelFeature,
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
    PromptMessageContentType,
    PromptMessageTool,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
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

    def _convert_prompt_message_to_dict(self, message: PromptMessage) -> dict:
        """
        Convert PromptMessage to dictionary format for Azure AI Studio API

        :param message: prompt message
        :return: message dict
        """
        if isinstance(message, UserPromptMessage):
            if isinstance(message.content, str):
                return {"role": "user", "content": message.content}
            elif isinstance(message.content, list):
                # Handle multimodal messages
                content = []
                for message_content in message.content:
                    if message_content.type == PromptMessageContentType.TEXT:
                        content.append({"type": "text", "text": message_content.data})
                    elif message_content.type == PromptMessageContentType.IMAGE:
                        # The content is a data URI (e.g., "data:image/png;base64,..."), which can be used directly.
                        content.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": message_content.data},
                            }
                        )
                return {"role": "user", "content": content}
            else:
                return {"role": "user", "content": ""}
        elif isinstance(message, AssistantPromptMessage):
            message_dict = {"role": "assistant", "content": message.content or ""}
            if message.tool_calls:
                message_dict["tool_calls"] = [
                    {
                        "id": tool_call.id,
                        "type": tool_call.type or "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments,
                        },
                    }
                    for tool_call in message.tool_calls
                ]
            return message_dict
        elif isinstance(message, SystemPromptMessage):
            return {"role": "system", "content": message.content}
        elif isinstance(message, ToolPromptMessage):
            return {
                "role": "tool",
                "content": message.content,
                "tool_call_id": message.tool_call_id,
            }
        else:
            raise ValueError(f"Unknown message type {type(message)}")

    def _convert_tools(self, tools: Sequence[PromptMessageTool]) -> list[dict]:
        """
        Convert PromptMessageTool to Azure AI Studio tool format

        :param tools: tool messages
        :return: tool dicts
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    def _convert_tool_calls(self, tool_calls) -> list[AssistantPromptMessage.ToolCall]:
        """
        Convert API tool calls to AssistantPromptMessage.ToolCall objects

        :param tool_calls: tool calls from API response
        :return: list of AssistantPromptMessage.ToolCall
        """
        result = []
        for tool_call in tool_calls:
            if hasattr(tool_call, "function"):
                result.append(
                    AssistantPromptMessage.ToolCall(
                        id=tool_call.id or "",
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=tool_call.function.name or "",
                            arguments=tool_call.function.arguments or "",
                        ),
                    )
                )
        return result

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
            api_version = credentials.get("api_version", "2024-05-01-preview")

            self.client = ChatCompletionsClient(
                endpoint=endpoint,
                credential=AzureKeyCredential(api_key),
                api_version=api_version,
            )
        messages = [
            self._convert_prompt_message_to_dict(msg) for msg in prompt_messages
        ]
        optional_fields = {}
        # GPT O series model don't support max_tokens parameter
        if "max_tokens" in model_parameters:
            optional_fields["max_tokens"] = model_parameters["max_tokens"]
        payload = {
            "messages": messages,
            "temperature": model_parameters.get("temperature", 0),
            "top_p": model_parameters.get("top_p", 1),
            "stream": stream,
            "model": model,
            **optional_fields,
        }
        if stop:
            payload["stop"] = stop
        if tools:
            payload["tools"] = self._convert_tools(tools)
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

                    # Handle content updates
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

                    # Handle tool calls if present
                    if hasattr(delta, "tool_calls") and delta.tool_calls:
                        tool_calls = self._convert_tool_calls(delta.tool_calls)
                        if tool_calls:
                            yield LLMResultChunk(
                                model=model,
                                prompt_messages=list(prompt_messages),
                                delta=LLMResultChunkDelta(
                                    index=0,
                                    message=AssistantPromptMessage(
                                        content="", tool_calls=tool_calls
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
        choice = response.choices[0]
        assistant_text = choice.message.content or ""

        # Handle tool calls if present
        tool_calls = []
        if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
            tool_calls = self._convert_tool_calls(choice.message.tool_calls)

        assistant_prompt_message = AssistantPromptMessage(
            content=assistant_text, tool_calls=tool_calls
        )

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
            api_version = credentials.get("api_version", "2024-05-01-preview")
            client = ChatCompletionsClient(
                endpoint=endpoint,
                credential=AzureKeyCredential(api_key),
                api_version=api_version,
            )
            client.complete(
                messages=[
                    {"role": "user", "content": "I say 'ping', you say 'pong'.ping"},
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

        # Add features based on credentials
        features = []
        if credentials.get("vision_support") == "true":
            features.append(ModelFeature.VISION)
        if credentials.get("function_call_support") == "true":
            features.append(ModelFeature.TOOL_CALL)
            features.append(ModelFeature.MULTI_TOOL_CALL)

        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_US=model),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.LLM,
            features=features,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(
                    credentials.get("context_size", "4096")
                ),
                ModelPropertyKey.MODE: credentials.get("mode", LLMMode.CHAT),
            },
            parameter_rules=rules,
        )
        return entity
