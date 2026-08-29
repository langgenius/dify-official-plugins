import logging
from collections.abc import Generator
from typing import Optional, Union, cast
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
from dify_plugin.entities.model.llm import LLMMode, LLMResult, LLMResultChunk, LLMResultChunkDelta
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
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeServerUnavailableError
from dify_plugin.interfaces.model.large_language_model import LargeLanguageModel
from openai import OpenAI, Stream
from openai.types.chat import ChatCompletion, ChatCompletionChunk, ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall
from models.common import CommonDeepInfra

logger = logging.getLogger(__name__)

class DeepInfraLargeLanguageModel(CommonDeepInfra, LargeLanguageModel):
    """
    Model class for DeepInfra large language model.
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
        return self._num_tokens_from_messages(model, prompt_messages, tools)

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
                messages=[{"role": "user", "content": "ping"}], model=model, temperature=0, max_tokens=10, stream=False
            )
        except Exception as e:
            raise CredentialsValidateFailedError(str(e))

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
        credentials_kwargs = self._to_credential_kwargs(credentials)
        client = OpenAI(**credentials_kwargs)
        extra_model_kwargs = {}
        if tools:
            # DeepInfra implements the current `tools` interface; the deprecated
            # `functions` parameter is ignored by the API.
            extra_model_kwargs["tools"] = [
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
        if stop:
            extra_model_kwargs["stop"] = stop
        if user:
            extra_model_kwargs["user"] = user
        if stream:
            # Without this the response carries no usage, and every streamed call falls back to
            # counting with a GPT-2 tokenizer -- which is the wrong vocabulary for every model
            # DeepInfra serves.
            extra_model_kwargs["stream_options"] = {"include_usage": True}
        response = client.chat.completions.create(
            messages=[self._convert_prompt_message_to_dict(m) for m in prompt_messages],
            model=model,
            stream=stream,
            **model_parameters,
            **extra_model_kwargs,
        )
        if stream:
            return self._handle_chat_generate_stream_response(model, credentials, response, prompt_messages, tools)
        return self._handle_chat_generate_response(model, credentials, response, prompt_messages, tools)

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
        if not response.choices:
            raise InvokeServerUnavailableError("Empty response from DeepInfra")
        assistant_message = response.choices[0].message
        tool_calls = self._extract_response_tool_calls(assistant_message.tool_calls or [])
        assistant_prompt_message = AssistantPromptMessage(content=assistant_message.content, tool_calls=tool_calls)
        if response.usage:
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
        else:
            prompt_tokens = self._num_tokens_from_messages(model, prompt_messages, tools)
            completion_tokens = self._num_tokens_from_messages(model, [assistant_prompt_message])
        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)
        response = LLMResult(
            model=response.model,
            prompt_messages=prompt_messages,
            message=assistant_prompt_message,
            usage=usage,
            system_fingerprint=response.system_fingerprint,
        )
        return response

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
        # tool_calls arrive split across chunks: the first carries id/name, later
        # ones append argument fragments. Accumulate them by index and emit once
        # the stream finishes.
        tool_call_buffer: dict[int, dict] = {}
        prompt_tokens = 0
        completion_tokens = 0
        final_tool_calls = []
        final_chunk = LLMResultChunk(
            model=model,
            prompt_messages=prompt_messages,
            delta=LLMResultChunkDelta(index=0, message=AssistantPromptMessage(content="")),
        )
        is_reasoning = False
        for chunk in response:
            # Usage is captured before the choices guard: DeepInfra can attach it to the finish
            # chunk as well as to a trailing choices-empty one, and reading it only in the latter
            # branch silently falls back to the GPT-2 estimate for every streamed call.
            if chunk.usage:
                prompt_tokens = chunk.usage.prompt_tokens
                completion_tokens = chunk.usage.completion_tokens
            if len(chunk.choices) == 0:
                continue
            delta = chunk.choices[0]
            has_finish_reason = delta.finish_reason is not None

            # Reasoning models stream their thinking in reasoning_content, leaving content empty
            # for most of the response. Surfacing it as <think> blocks keeps the user from staring
            # at a silent gap while being billed for the tokens.
            # model_dump() carries reasoning_content through model_extra, since the SDK does not
            # declare it. The fallback reads the attributes directly rather than defaulting to an
            # empty dict, which would silently discard the whole response instead of just the
            # reasoning.
            if hasattr(delta.delta, "model_dump"):
                delta_dict = delta.delta.model_dump()
            else:
                delta_dict = {
                    "content": getattr(delta.delta, "content", None),
                    "reasoning_content": getattr(delta.delta, "reasoning_content", None),
                    "tool_calls": getattr(delta.delta, "tool_calls", None),
                }
            content, is_reasoning = self._wrap_thinking_by_reasoning_content(delta_dict, is_reasoning)

            for delta_tool_call in delta.delta.tool_calls or []:
                slot = tool_call_buffer.setdefault(
                    delta_tool_call.index, {"id": "", "type": "function", "name": "", "arguments": ""}
                )
                if delta_tool_call.id:
                    slot["id"] = delta_tool_call.id
                if delta_tool_call.type:
                    slot["type"] = delta_tool_call.type
                if delta_tool_call.function:
                    if delta_tool_call.function.name:
                        slot["name"] = delta_tool_call.function.name
                    if delta_tool_call.function.arguments:
                        slot["arguments"] += delta_tool_call.function.arguments

            if not has_finish_reason and not content:
                continue

            tool_calls = []
            if has_finish_reason and tool_call_buffer:
                tool_calls = self._drain_tool_call_buffer(tool_call_buffer)
                final_tool_calls.extend(tool_calls)
            assistant_prompt_message = AssistantPromptMessage(content=content, tool_calls=tool_calls)
            full_assistant_content += content
            if has_finish_reason:
                final_chunk = LLMResultChunk(
                    model=chunk.model,
                    prompt_messages=prompt_messages,
                    system_fingerprint=chunk.system_fingerprint,
                    delta=LLMResultChunkDelta(
                        index=delta.index, message=assistant_prompt_message, finish_reason=delta.finish_reason
                    ),
                )
            else:
                yield LLMResultChunk(
                    model=chunk.model,
                    prompt_messages=prompt_messages,
                    system_fingerprint=chunk.system_fingerprint,
                    delta=LLMResultChunkDelta(index=delta.index, message=assistant_prompt_message),
                )
        # A stream that ends without a finish_reason chunk would otherwise drop a fully
        # reassembled tool call on the floor, with no error anywhere.
        if tool_call_buffer and not final_tool_calls:
            leftover = self._drain_tool_call_buffer(tool_call_buffer)
            final_tool_calls.extend(leftover)
            final_chunk.delta.message.tool_calls = leftover

        if not prompt_tokens:
            prompt_tokens = self._num_tokens_from_messages(model, prompt_messages, tools)
        if not completion_tokens:
            full_assistant_prompt_message = AssistantPromptMessage(
                content=full_assistant_content, tool_calls=final_tool_calls
            )
            completion_tokens = self._num_tokens_from_messages(model, [full_assistant_prompt_message])
        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)
        final_chunk.delta.usage = usage
        yield final_chunk

    @staticmethod
    def _drain_tool_call_buffer(buffer: dict[int, dict]) -> list[AssistantPromptMessage.ToolCall]:
        """Turn accumulated streaming fragments into tool calls, ordered by their index."""
        return [
            AssistantPromptMessage.ToolCall(
                id=slot["id"],
                type=slot["type"],
                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                    name=slot["name"], arguments=slot["arguments"]
                ),
            )
            for _, slot in sorted(buffer.items())
        ]

    def _extract_response_tool_calls(
        self, response_tool_calls: list[ChatCompletionMessageToolCall | ChoiceDeltaToolCall]
    ) -> list[AssistantPromptMessage.ToolCall]:
        """
        Extract tool calls from response

        :param response_tool_calls: response tool calls
        :return: list of tool calls
        """
        tool_calls = []
        if response_tool_calls:
            for response_tool_call in response_tool_calls:
                function = AssistantPromptMessage.ToolCall.ToolCallFunction(
                    name=response_tool_call.function.name, arguments=response_tool_call.function.arguments
                )
                tool_call = AssistantPromptMessage.ToolCall(
                    id=response_tool_call.id, type=response_tool_call.type, function=function
                )
                tool_calls.append(tool_call)
        return tool_calls

    def _convert_prompt_message_to_dict(self, message: PromptMessage) -> dict:
        """
        Convert PromptMessage to dict for DeepInfra API
        """
        if isinstance(message, UserPromptMessage):
            message = cast(UserPromptMessage, message)
            if isinstance(message.content, str):
                message_dict = {"role": "user", "content": message.content}
            else:
                sub_messages = []
                for message_content in message.content:
                    if message_content.type == PromptMessageContentType.TEXT:
                        message_content = cast(TextPromptMessageContent, message_content)
                        sub_message_dict = {"type": "text", "text": message_content.data}
                        sub_messages.append(sub_message_dict)
                    elif message_content.type == PromptMessageContentType.IMAGE:
                        message_content = cast(ImagePromptMessageContent, message_content)
                        sub_message_dict = {
                            "type": "image_url",
                            "image_url": {"url": message_content.data, "detail": message_content.detail.value},
                        }
                        sub_messages.append(sub_message_dict)
                message_dict = {"role": "user", "content": sub_messages}
        elif isinstance(message, AssistantPromptMessage):
            message = cast(AssistantPromptMessage, message)
            message_dict = {"role": "assistant", "content": message.content}
            if message.tool_calls:
                message_dict["tool_calls"] = [
                    {
                        "id": tool_call.id,
                        "type": tool_call.type,
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments,
                        },
                    }
                    for tool_call in message.tool_calls
                ]
        elif isinstance(message, SystemPromptMessage):
            message = cast(SystemPromptMessage, message)
            message_dict = {"role": "system", "content": message.content}
        elif isinstance(message, ToolPromptMessage):
            message = cast(ToolPromptMessage, message)
            message_dict = {"role": "tool", "content": message.content, "tool_call_id": message.tool_call_id}
        else:
            raise ValueError(f"Got unknown type {message}")
        if message.name:
            message_dict["name"] = message.name
        return message_dict

    def _num_tokens_from_messages(
        self,
        model: str,
        messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
        credentials: Optional[dict] = None,
    ) -> int:
        """
        Approximate num tokens with GPT2 tokenizer.
        """
        tokens_per_message = 3
        tokens_per_name = 1
        num_tokens = 0
        messages_dict = [self._convert_prompt_message_to_dict(m) for m in messages]
        for message in messages_dict:
            num_tokens += tokens_per_message
            for key, value in message.items():
                # tool_calls is itself a list, so it has to be recognised before the generic list
                # flattening below -- otherwise it is collapsed to "" and every tool call counts
                # as zero tokens.
                if key != "tool_calls" and isinstance(value, list):
                    text = ""
                    for item in value:
                        if isinstance(item, dict) and item["type"] == "text":
                            text += item["text"]
                    value = text
                if key == "tool_calls":
                    for tool_call in value:
                        for t_key, t_value in tool_call.items():
                            num_tokens += self._get_num_tokens_by_gpt2(t_key)
                            if t_key == "function":
                                for f_key, f_value in t_value.items():
                                    num_tokens += self._get_num_tokens_by_gpt2(f_key)
                                    num_tokens += self._get_num_tokens_by_gpt2(f_value)
                            else:
                                num_tokens += self._get_num_tokens_by_gpt2(t_key)
                                num_tokens += self._get_num_tokens_by_gpt2(t_value)
                else:
                    num_tokens += self._get_num_tokens_by_gpt2(str(value))
                if key == "name":
                    num_tokens += tokens_per_name
        num_tokens += 3
        if tools:
            num_tokens += self._num_tokens_for_tools(tools)
        return num_tokens

    def _num_tokens_for_tools(self, tools: list[PromptMessageTool]) -> int:
        """
        Calculate num tokens for tool calling with tiktoken package.

        :param tools: tools for tool calling
        :return: number of tokens
        """
        num_tokens = 0
        for tool in tools:
            num_tokens += self._get_num_tokens_by_gpt2("type")
            num_tokens += self._get_num_tokens_by_gpt2("function")
            num_tokens += self._get_num_tokens_by_gpt2("function")
            num_tokens += self._get_num_tokens_by_gpt2("name")
            num_tokens += self._get_num_tokens_by_gpt2(tool.name)
            num_tokens += self._get_num_tokens_by_gpt2("description")
            num_tokens += self._get_num_tokens_by_gpt2(tool.description)
            parameters = tool.parameters
            num_tokens += self._get_num_tokens_by_gpt2("parameters")
            if "title" in parameters:
                num_tokens += self._get_num_tokens_by_gpt2("title")
                num_tokens += self._get_num_tokens_by_gpt2(parameters.get("title"))
            num_tokens += self._get_num_tokens_by_gpt2("type")
            num_tokens += self._get_num_tokens_by_gpt2(parameters.get("type"))
            if "properties" in parameters:
                num_tokens += self._get_num_tokens_by_gpt2("properties")
                for key, value in parameters.get("properties").items():
                    num_tokens += self._get_num_tokens_by_gpt2(key)
                    for field_key, field_value in value.items():
                        num_tokens += self._get_num_tokens_by_gpt2(field_key)
                        if field_key == "enum":
                            for enum_field in field_value:
                                num_tokens += 3
                                num_tokens += self._get_num_tokens_by_gpt2(enum_field)
                        else:
                            num_tokens += self._get_num_tokens_by_gpt2(field_key)
                            num_tokens += self._get_num_tokens_by_gpt2(str(field_value))
            if "required" in parameters:
                num_tokens += self._get_num_tokens_by_gpt2("required")
                for required_field in parameters["required"]:
                    num_tokens += 3
                    num_tokens += self._get_num_tokens_by_gpt2(required_field)
        return num_tokens

    def get_customizable_model_schema(self, model: str, credentials: dict) -> AIModelEntity:
        features = []
        if credentials.get("function_calling_type") == "function_call":
            features.extend(
                [ModelFeature.TOOL_CALL, ModelFeature.MULTI_TOOL_CALL, ModelFeature.STREAM_TOOL_CALL]
            )
        if credentials.get("vision_support") == "support":
            features.append(ModelFeature.VISION)

        return AIModelEntity(
            model=model,
            label=I18nObject(
                en_us=credentials.get("model_label_en_US", model),
                zh_hans=credentials.get("model_label_zh_Hans", model),
            ),
            model_type=ModelType.LLM,
            features=features,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(credentials.get("context_size", 4096)),
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    use_template="temperature",
                    label=I18nObject(en_us="Temperature", zh_hans="温度"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="max_tokens",
                    use_template="max_tokens",
                    default=512,
                    min=1,
                    max=int(credentials.get("max_tokens", 4096)),
                    label=I18nObject(en_us="Max Tokens", zh_hans="最大标记"),
                    type=ParameterType.INT,
                ),
                ParameterRule(
                    name="top_p",
                    use_template="top_p",
                    label=I18nObject(en_us="Top P", zh_hans="Top P"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="top_k",
                    use_template="top_k",
                    label=I18nObject(en_us="Top K", zh_hans="Top K"),
                    type=ParameterType.FLOAT,
                ),
            ],
        )
