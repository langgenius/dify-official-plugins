# Copyright (c) Meta Platforms, Inc. and affiliates
import logging
from collections.abc import Generator
from typing import cast, Optional, Union

import openai

from dify_plugin import LargeLanguageModel
from dify_plugin.entities import I18nObject
from dify_plugin.entities.model import AIModelEntity, FetchFrom, ModelType
from dify_plugin.entities.model.llm import (
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
)
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageContentType,
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
from openai import OpenAI, Stream
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessageToolCall,
)
from openai.types.chat.chat_completion_chunk import (
    ChoiceDeltaFunctionCall,
    ChoiceDeltaToolCall,
)
from openai.types.chat.chat_completion_message import FunctionCall

logger = logging.getLogger(__name__)


class LlamaApiLargeLanguageModel(LargeLanguageModel):
    """
    Model class for llama-api large language model.
    """

    def _to_credential_kwargs(self, credentials: dict) -> dict:
        """
        Transform credentials to kwargs for model instance

        :param credentials:
        :return:
        """
        credentials_kwargs = {
            "api_key": credentials["llama_api_key"],
            "base_url": "https://api.llama.com/compat/v1",
            "max_retries": 1,
        }

        return credentials_kwargs

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

        return self._chat_generate(
            model=model,
            credentials=credentials,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user,
        )
    
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
        return self._num_tokens_from_messages(
                model, prompt_messages, tools
            )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            credentials_kwargs = self._to_credential_kwargs(credentials)
            client = OpenAI(**credentials_kwargs)
            client.chat.completions.create(
                messages=[{"role": "user", "content": "ping"}],
                model=model,
                temperature=0,
                max_tokens=10,
                stream=False,
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

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
            InvokeConnectionError: [openai.APIConnectionError, openai.APITimeoutError],
            InvokeServerUnavailableError: [openai.InternalServerError],
            InvokeRateLimitError: [openai.RateLimitError],
            InvokeAuthorizationError: [
                openai.AuthenticationError,
                openai.PermissionDeniedError,
            ],
            InvokeBadRequestError: [
                openai.BadRequestError,
                openai.NotFoundError,
                openai.UnprocessableEntityError,
                openai.APIError,
            ],
        }

    def _chat_generate(
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
        Invoke llm chat model

        :param model: model name
        :param credentials: credentials
        :param prompt_messages: prompt messages
        :param model_parameters: model parameters
        :param tools: tools for tool calling
        :param stop: stop words
        :param stream: is stream response
        :param user: unique user id
        :return: full response or stream response chunk generator result
        """
        # transform credentials to kwargs for model instance
        credentials_kwargs = self._to_credential_kwargs(credentials)

        # init model client
        client = OpenAI(**credentials_kwargs)

        response_format = model_parameters.get("response_format")
        if response_format:
            if response_format == "json_schema":
                json_schema = model_parameters.get("json_schema")
                if not json_schema:
                    raise ValueError("Must define JSON Schema when the response format is json_schema")
                try:
                    schema = json.loads(json_schema)
                except Exception:
                    raise ValueError(f"not correct json_schema format: {json_schema}")
                model_parameters.pop("json_schema")
                model_parameters["response_format"] = {"type": "json_schema", "json_schema": schema}
            else:
                model_parameters["response_format"] = {"type": response_format}
        elif "json_schema" in model_parameters:
            del model_parameters["json_schema"]

        formatted_tools = []
        if tools:
            formatted_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters
                    }
                }
                for tool in tools
            ]
        
        # chat model
        response = client.chat.completions.create(
            messages=[self._convert_prompt_message_to_dict(m) for m in prompt_messages],  # type: ignore
            model=model,
            stream=stream,
            tools=formatted_tools,
            **model_parameters,
        )  # type: ignore

        if stream:
            return self._handle_chat_generate_stream_response(
                model, credentials, response, prompt_messages, tools
            )

        block_result = self._handle_chat_generate_response(
            model, credentials, response, prompt_messages, tools
        )

        return block_result

    def _handle_chat_generate_response(
        self,
        model: str,
        credentials: dict,
        response: ChatCompletion,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> LLMResult:
        """
        Handle llm chat response

        :param model: model name
        :param credentials: credentials
        :param response: response
        :param prompt_messages: prompt messages
        :param tools: tools for tool calling
        :return: llm response
        """
        assistant_message = response.choices[0].message
        assistant_message_tool_calls = assistant_message.tool_calls
        # extract tool calls from response
        tool_calls = self._extract_response_tool_calls(assistant_message_tool_calls)

        # transform assistant message to prompt message
        assistant_prompt_message = AssistantPromptMessage(
            content=assistant_message.content, tool_calls=tool_calls
        )

        # calculate num tokens
        if response.usage:
            # transform usage
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
        else:
            # calculate num tokens
            prompt_tokens = self._num_tokens_from_messages(
                model, prompt_messages, tools
            )
            completion_tokens = self._num_tokens_from_messages(
                model, [assistant_prompt_message]
            )

        # transform usage
        usage = self._calc_response_usage(
            model, credentials, prompt_tokens, completion_tokens
        )

        # transform response
        return LLMResult(
            model=response.model,
            prompt_messages=prompt_messages,
            message=assistant_prompt_message,
            usage=usage,
            system_fingerprint=response.system_fingerprint,
        )

    def _convert_prompt_message_to_dict(self, message: PromptMessage) -> dict:
        """
        Convert PromptMessage to dict for OpenAI API
        """
        if isinstance(message, UserPromptMessage):
            message = cast(UserPromptMessage, message)
            if isinstance(message.content, str):
                message_dict = {"role": "user", "content": message.content}
            else:
                sub_messages = []
                assert isinstance(message.content, list)
                for message_content in message.content:
                    if message_content.type == PromptMessageContentType.TEXT:
                        message_content = cast(
                            TextPromptMessageContent, message_content
                        )
                        sub_message_dict = {
                            "type": "text",
                            "text": message_content.data,
                        }
                        sub_messages.append(sub_message_dict)
                    elif message_content.type == PromptMessageContentType.IMAGE:
                        message_content = cast(
                            ImagePromptMessageContent, message_content
                        )
                        sub_message_dict = {
                            "type": "image_url",
                            "image_url": {
                                "url": message_content.data,
                                "detail": message_content.detail.value,
                            },
                        }
                        sub_messages.append(sub_message_dict)

                message_dict = {"role": "user", "content": sub_messages}
        elif isinstance(message, AssistantPromptMessage):
            message = cast(AssistantPromptMessage, message)
            message_dict = {"role": "assistant", "content": message.content}
            if message.tool_calls:
                message_dict["tool_calls"] = [tool_call.dict() for tool_call in
                                              message.tool_calls]
        elif isinstance(message, SystemPromptMessage):
            message = cast(SystemPromptMessage, message)
            message_dict = {"role": "system", "content": message.content}
        elif isinstance(message, ToolPromptMessage):
            message = cast(ToolPromptMessage, message)
            message_dict = {
                "role": "tool",
                "content": message.content,
                "tool_call_id": message.tool_call_id
            }
        else:
            raise ValueError(f"Got unknown type {message}")

        if message.name:
            message_dict["name"] = message.name
        return message_dict

    def _handle_chat_generate_stream_response(
        self,
        model: str,
        credentials: dict,
        response: Stream[ChatCompletionChunk],
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> Generator:
        """
        Handle llm chat stream response

        :param model: model name
        :param response: response
        :param prompt_messages: prompt messages
        :param tools: tools for tool calling
        :return: llm response chunk generator
        """
        full_assistant_content = ""
        delta_assistant_message_function_call_storage: Optional[
            ChoiceDeltaFunctionCall
        ] = None
        prompt_tokens = 0
        completion_tokens = 0
        final_tool_calls = []
        final_chunk = LLMResultChunk(
            model=model,
            prompt_messages=prompt_messages,
            delta=LLMResultChunkDelta(
                index=0,
                message=AssistantPromptMessage(content=""),
            ),
        )

        for chunk in response:
            if len(chunk.choices) == 0:
                if chunk.usage:
                    # calculate num tokens
                    prompt_tokens = chunk.usage.prompt_tokens
                    completion_tokens = chunk.usage.completion_tokens
                continue

            delta = chunk.choices[0]
            has_finish_reason = delta.finish_reason is not None
            if (
                not has_finish_reason
                and (delta.delta.content is None or delta.delta.content == "")
                and delta.delta.function_call is None
            ):
                continue

            assistant_message_tool_calls = delta.delta.tool_calls
            assistant_message_function_call = delta.delta.function_call
            # extract tool calls from response
            if delta_assistant_message_function_call_storage is not None:
                # handle process of stream function call
                if assistant_message_function_call:
                    # message has not ended ever
                    assert isinstance(
                        delta_assistant_message_function_call_storage.arguments, str
                    )
                    assert isinstance(assistant_message_function_call.arguments, str)

                    delta_assistant_message_function_call_storage.arguments += (
                        assistant_message_function_call.arguments
                    )
                    continue
                else:
                    # message has ended
                    assistant_message_function_call = (
                        delta_assistant_message_function_call_storage
                    )
                    delta_assistant_message_function_call_storage = None
            else:
                if assistant_message_function_call:
                    # start of stream function call
                    delta_assistant_message_function_call_storage = (
                        assistant_message_function_call
                    )
                    if delta_assistant_message_function_call_storage.arguments is None:
                        delta_assistant_message_function_call_storage.arguments = ""
                    if not has_finish_reason:
                        continue

            tool_calls = self._extract_response_tool_calls(assistant_message_tool_calls)
            if tool_calls:
                final_tool_calls.extend(tool_calls)

            # transform assistant message to prompt message
            assistant_prompt_message = AssistantPromptMessage(
                content=delta.delta.content if delta.delta.content else "",
                tool_calls=tool_calls,
            )

            full_assistant_content += delta.delta.content if delta.delta.content else ""

            if has_finish_reason:
                final_chunk = LLMResultChunk(
                    model=chunk.model,
                    prompt_messages=prompt_messages,
                    system_fingerprint=chunk.system_fingerprint,
                    delta=LLMResultChunkDelta(
                        index=delta.index,
                        message=assistant_prompt_message,
                        finish_reason=delta.finish_reason,
                    ),
                )
            else:
                yield LLMResultChunk(
                    model=chunk.model,
                    prompt_messages=prompt_messages,
                    system_fingerprint=chunk.system_fingerprint,
                    delta=LLMResultChunkDelta(
                        index=delta.index,
                        message=assistant_prompt_message,
                    ),
                )

        if not prompt_tokens:
            prompt_tokens = self._num_tokens_from_messages(
                model, prompt_messages, tools
            )

        if not completion_tokens:
            full_assistant_prompt_message = AssistantPromptMessage(
                content=full_assistant_content, tool_calls=final_tool_calls
            )
            completion_tokens = self._num_tokens_from_messages(
                model, [full_assistant_prompt_message]
            )

        # transform usage
        usage = self._calc_response_usage(
            model, credentials, prompt_tokens, completion_tokens
        )
        final_chunk.delta.usage = usage

        yield final_chunk

    def _num_tokens_from_messages(
        self,
        model: str,
        messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        num_tokens = 0
        messages_dict = [self._convert_prompt_message_to_dict(m) for m in messages]
        for message in messages_dict:
            num_tokens += self._get_num_tokens_by_gpt2(str(message))
        return num_tokens

    def _extract_response_tool_calls(
        self,
        response_tool_calls: list[ChatCompletionMessageToolCall | ChoiceDeltaToolCall],
    ) -> list[AssistantPromptMessage.ToolCall]:
        """
        Extract tool calls from response

        :param response_tool_calls: response tool calls
        :return: list of tool calls
        """
        tool_calls = []
        if response_tool_calls:
            for response_tool_call in response_tool_calls:
                assert isinstance(response_tool_call, ChatCompletionMessageToolCall)
                function = AssistantPromptMessage.ToolCall.ToolCallFunction(
                    name=response_tool_call.function.name,
                    arguments=response_tool_call.function.arguments,
                )

                tool_call = AssistantPromptMessage.ToolCall(
                    id=response_tool_call.id,
                    type=response_tool_call.type,
                    function=function,
                )
                tool_calls.append(tool_call)

        return tool_calls