from collections.abc import Generator
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from dify_plugin.interfaces.model.large_language_model import LargeLanguageModel
from models.llm.chat_completion import MinimaxChatCompletion
from models.llm.chat_completion_pro import MinimaxChatCompletionPro
from models.llm.chat_completion_v2 import MinimaxChatCompletionV2
from models.llm.errors import (
    BadRequestError,
    InsufficientAccountBalanceError,
    InternalServerError,
    InvalidAPIKeyError,
    InvalidAuthenticationError,
    RateLimitReachedError,
)
from models.llm.types import MinimaxMessage


class MinimaxLargeLanguageModel(LargeLanguageModel):
    model_apis = {
        "minimax-m1": MinimaxChatCompletionV2,
        "minimax-text-01": MinimaxChatCompletionPro,
        "abab7-chat-preview": MinimaxChatCompletionPro,
        "abab6.5s-chat": MinimaxChatCompletionPro,
        "abab6.5t-chat": MinimaxChatCompletionPro,
        "abab6.5-chat": MinimaxChatCompletionPro,
        "abab6-chat": MinimaxChatCompletionPro,
        "abab5.5s-chat": MinimaxChatCompletionPro,
        "abab5.5-chat": MinimaxChatCompletionPro,
        "abab5-chat": MinimaxChatCompletion,
    }

    def _invoke(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: list[PromptMessageTool] | None = None,
        stop: list[str] | None = None,
        stream: bool = True,
        user: str | None = None,
    ) -> LLMResult | Generator:
        return self._generate(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate credentials for Minimax model
        """
        if model not in self.model_apis:
            raise CredentialsValidateFailedError(f"Invalid model: {model}")
        if not credentials.get("minimax_api_key"):
            raise CredentialsValidateFailedError("Invalid API key")
        if not credentials.get("minimax_group_id"):
            raise CredentialsValidateFailedError("Invalid group ID")

        # Use the correct class based on the model
        instance = self.model_apis[model]()

        # Get endpoint_url from credentials, use default if not provided
        endpoint_url = credentials.get("endpoint_url", "https://api.minimaxi.com/")

        try:
            instance.generate(
                model=model,
                api_key=credentials["minimax_api_key"],
                group_id=credentials["minimax_group_id"],
                endpoint_url=endpoint_url,
                prompt_messages=[MinimaxMessage(content="ping", role="USER")],
                model_parameters={"max_tokens": 50},
                tools=[],
                stop=[],
                stream=False,
                user="",
            )
        except (InvalidAuthenticationError, InsufficientAccountBalanceError) as e:
            raise CredentialsValidateFailedError(f"Invalid API key: {e}")

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> int:
        return self._num_tokens_from_messages(prompt_messages, tools, model)

    def _num_tokens_from_messages(self, messages: list[PromptMessage], tools: list[PromptMessageTool], model: str = None) -> int:
        """
        Calculate num tokens for minimax model

        not like ChatGLM, Minimax has a special prompt structure, we could not find a proper way
        to calculate the num tokens, so we use str() to convert the prompt to string

        Minimax does not provide their own tokenizer of adab5.5 and abab5 model
        therefore, we use gpt2 tokenizer instead
        """
        messages_dict = [self._convert_prompt_message_to_minimax_message(m, model).to_dict() for m in messages]
        return self._get_num_tokens_by_gpt2(str(messages_dict))

    def _generate(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: list[PromptMessageTool] | None = None,
        stop: list[str] | None = None,
        stream: bool = True,
        user: str | None = None,
    ) -> LLMResult | Generator:
        """
        Generate response using the appropriate client class for the model
        """
        # Use the correct class based on the model
        client = self.model_apis[model]()
        if tools:
            tools = [
                {"name": tool.name, "description": tool.description, "parameters": tool.parameters} for tool in tools
            ]

        # Get endpoint_url from credentials, use default if not provided
        endpoint_url = credentials.get("endpoint_url", "https://api.minimax.chat/")

        response = client.generate(
            model=model,
            api_key=credentials["minimax_api_key"],
            group_id=credentials["minimax_group_id"],
            endpoint_url=endpoint_url,
            prompt_messages=[self._convert_prompt_message_to_minimax_message(message, model) for message in prompt_messages],
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user,
        )
        if stream:
            return self._handle_chat_generate_stream_response(
                model=model, prompt_messages=prompt_messages, credentials=credentials, response=response
            )
        return self._handle_chat_generate_response(
            model=model, prompt_messages=prompt_messages, credentials=credentials, response=response
        )

    def _convert_prompt_message_to_minimax_message(self, prompt_message: PromptMessage, model: str = None) -> MinimaxMessage:
        """
        convert PromptMessage to MinimaxMessage so that we can use the appropriate client interface
        """
        # Extract content as string, handling None and list cases
        content = self._extract_text_content(prompt_message.content)

        if isinstance(prompt_message, SystemPromptMessage):
            return MinimaxMessage(role=MinimaxMessage.Role.SYSTEM.value, content=content)
        elif isinstance(prompt_message, UserPromptMessage):
            return MinimaxMessage(role=MinimaxMessage.Role.USER.value, content=content)
        elif isinstance(prompt_message, AssistantPromptMessage):
            message = MinimaxMessage(role=MinimaxMessage.Role.ASSISTANT.value, content=content)
            if prompt_message.tool_calls:
                # Determine how to handle tool calls based on API type
                api_class = self.model_apis.get(model) if model else None
                if api_class == MinimaxChatCompletionV2:
                    # V2 API supports multiple tool calls
                    message.tool_calls = [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in prompt_message.tool_calls
                    ]
                elif api_class == MinimaxChatCompletionPro:
                    # Pro API uses function_call format, taking only the first tool call
                    if prompt_message.tool_calls:
                        tc = prompt_message.tool_calls[0]  # Pro API typically supports only single function call
                        message.function_call = {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                # Original API (MinimaxChatCompletion) does not support tool calls, ignore
            return message
        elif isinstance(prompt_message, ToolPromptMessage):
            message = MinimaxMessage(role=MinimaxMessage.Role.FUNCTION.value, content=content)
            # Set corresponding fields based on API type
            api_class = self.model_apis.get(model) if model else None
            if api_class == MinimaxChatCompletionV2:
                # V2 API requires tool_call_id
                message.tool_call_id = prompt_message.tool_call_id
            # Pro API and original API do not require special handling for tool messages
            return message
        else:
            raise NotImplementedError(f"Prompt message type {type(prompt_message)} is not supported")

    def _extract_text_content(self, content) -> str:
        """
        Extract text content from PromptMessage content field

        :param content: content field from PromptMessage (can be None, str, or list)
        :return: text content as string
        """
        if content is None:
            return ""
        elif isinstance(content, str):
            return content
        elif isinstance(content, list):
            # Handle multimodal content - extract text parts
            text_parts = []
            for item in content:
                if isinstance(item, TextPromptMessageContent):
                    # This is a TextPromptMessageContent object
                    text_parts.append(item.data)
                elif hasattr(item, 'type') and hasattr(item, 'data'):
                    # This is another PromptMessageContent object
                    if item.type == "text":
                        text_parts.append(item.data)
                elif isinstance(item, dict) and item.get('type') == 'text':
                    # This is a dict with text content
                    text_parts.append(item.get('data', ''))
            return ' '.join(text_parts) if text_parts else ""
        else:
            # Fallback: convert to string
            return str(content)

    def _handle_chat_generate_response(
        self, model: str, prompt_messages: list[PromptMessage], credentials: dict, response: MinimaxMessage
    ) -> LLMResult:
        usage = self._calc_response_usage(
            model=model,
            credentials=credentials,
            prompt_tokens=response.usage["prompt_tokens"],
            completion_tokens=response.usage["completion_tokens"],
        )

        tool_calls = []
        if response.tool_calls:
            # Handle v2 API tool calls format
            for tc in response.tool_calls:
                tool_calls.append(
                    AssistantPromptMessage.ToolCall(
                        id=tc.get("id", ""),
                        type=tc.get("type", "function"),
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=tc.get("function", {}).get("name", ""),
                            arguments=tc.get("function", {}).get("arguments", "{}"),
                        ),
                    )
                )
        elif response.function_call:
            # Handle Pro API function_call format
            tool_calls.append(
                AssistantPromptMessage.ToolCall(
                    id="",  # Pro API has no ID concept, use empty string
                    type="function",
                    function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                        name=response.function_call.get("name", ""),
                        arguments=response.function_call.get("arguments", "{}"),
                    ),
                )
            )

        return LLMResult(
            model=model,
            prompt_messages=prompt_messages,
            message=AssistantPromptMessage(content=response.content, tool_calls=tool_calls),
            usage=usage,
        )

    def _handle_chat_generate_stream_response(
        self,
        model: str,
        prompt_messages: list[PromptMessage],
        credentials: dict,
        response: Generator[MinimaxMessage, None, None],
    ) -> Generator[LLMResultChunk, None, None]:
        for message in response:
            if message.usage:
                usage = self._calc_response_usage(
                    model=model,
                    credentials=credentials,
                    prompt_tokens=message.usage["prompt_tokens"],
                    completion_tokens=message.usage["completion_tokens"],
                )
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(content=message.content, tool_calls=[]),
                        usage=usage,
                        finish_reason=message.stop_reason or None,
                    ),
                )
            elif message.tool_calls or message.function_call:
                # Handle tool calls in streaming (both v2 API and Pro API)
                tool_calls = []
                if message.tool_calls:
                    # V2 API tool calls format
                    for tc in message.tool_calls:
                        tool_calls.append(
                            AssistantPromptMessage.ToolCall(
                                id=tc.get("id", ""),
                                type=tc.get("type", "function"),
                                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                    name=tc.get("function", {}).get("name", ""),
                                    arguments=tc.get("function", {}).get("arguments", "{}"),
                                ),
                            )
                        )
                elif message.function_call:
                    # Pro API function_call format
                    tool_calls.append(
                        AssistantPromptMessage.ToolCall(
                            id="",  # Pro API has no ID concept, use empty string
                            type="function",
                            function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                name=message.function_call.get("name", ""),
                                arguments=message.function_call.get("arguments", "{}"),
                            ),
                        )
                    )

                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(content="", tool_calls=tool_calls),
                        finish_reason=None,
                    ),
                )
            else:
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(content=message.content, tool_calls=[]),
                        finish_reason=message.stop_reason or None,
                    ),
                )

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
            InvokeConnectionError: [],
            InvokeServerUnavailableError: [InternalServerError],
            InvokeRateLimitError: [RateLimitReachedError],
            InvokeAuthorizationError: [InvalidAuthenticationError, InsufficientAccountBalanceError, InvalidAPIKeyError],
            InvokeBadRequestError: [BadRequestError, KeyError],
        }
