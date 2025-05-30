import logging
from collections.abc import Generator
from typing import Optional, Union, Any

from dify_plugin import LargeLanguageModel
from dify_plugin.entities import I18nObject
from dify_plugin.errors.model import (
    CredentialsValidateFailedError, InvokeError,
)
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    ModelType,
)
from dify_plugin.entities.model.llm import (
    LLMResult, LLMResultChunk, LLMResultChunkDelta,
)
from dify_plugin.entities.model.message import (
    PromptMessage,
    PromptMessageTool, AssistantPromptMessage,
)

from openai import OpenAI, Stream
from openai.types.chat import ChatCompletionToolParam, ChatCompletion, ChatCompletionChunk
from openai.types.shared_params import FunctionDefinition

logger = logging.getLogger(__name__)


class BaiduQianfanLargeLanguageModel(LargeLanguageModel):
    """
    Model class for baidu_qianfan large language model.
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

        client = OpenAI(
            api_key=credentials["api_key"],
            base_url="https://qianfan.baidubce.com/v2",
        )

        messages: list[dict[str, any]] = [
            # 因为 role 不是 json 可序列化的，所以单独提出来
            {**m.model_dump(exclude={"role"}), "role": m.role.value}
            for m in prompt_messages
        ]
        wrapped_tools: list[ChatCompletionToolParam] = \
            [
                ChatCompletionToolParam(
                    type="function",
                    function=FunctionDefinition(**f.model_dump()),
                ) for f in tools
            ] if tools is not None else []

        handler: Union[ChatCompletion, Stream[ChatCompletionChunk]] = \
            client.chat.completions.create(
                model=model,
                messages=messages,
                stop=stop,
                user=user,
                tools=wrapped_tools,
                stream_options={"include_usage": True},
                stream=stream,
                **model_parameters,
            )

        if stream:
            assert isinstance(handler, Stream), f"unexpected handler type mismatched: {type(handler)}"

            for i in self._handle_chat_generate_stream_response(model, credentials, handler, prompt_messages):
                yield i

            return

        return self._handle_chat_generate_stream_response(model, credentials, handler, prompt_messages)

   
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
        if credentials.get("api_key", None) is None or len(credentials["api_key"]) == 0:
            raise CredentialsValidateFailedError()

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
        return {}


    def _handle_chat_generate_stream_response(
        self,
        model: str,
        credentials: dict,
        response: Stream[ChatCompletionChunk],
        prompt_messages: list[PromptMessage],
    ) -> Generator:
        """
        Handle llm chat stream response

        :param model: model name
        :param response: response
        :param prompt_messages: prompt messages
        :param tools: tools for tool calling
        :return: llm response chunk generator
        """
        prompt_tokens, completion_tokens = 0, 0
        merged_tool_calls: list[AssistantPromptMessage.ToolCall] = []
        function_list: list[AssistantPromptMessage.Function] = []

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
                and delta.delta.tool_calls is None
            ):
                continue

            tool_calls: list[AssistantPromptMessage.ToolCall] = []
            if delta.delta.tool_calls is not None and len(delta.delta.tool_calls) > 0:
                for i in range(len(delta.delta.tool_calls)):
                    function = delta.delta.tool_calls[i].function
                    function_name = function.name if function.name is not None else ""
                    function_arguments = function.arguments if function.arguments is not None else ""

                    if len(function_list) <= i:
                        function_list.append(AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=function_name,
                            arguments=function_arguments
                        ))
                    else:
                        function_list[i].name += function_name
                        function_list[i].arguments += function_arguments

                tool_calls = [
                    AssistantPromptMessage.ToolCall(
                        id=tool_call.id,
                        type=tool_call.type,
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=tool_call.function.name,
                            arguments=tool_call.function.arguments,
                        )
                    ) for tool_call in delta.delta.tool_calls
                ]

                merged_tool_calls = tool_calls

            # transform assistant message to prompt message
            assistant_prompt_message = AssistantPromptMessage(
                content=delta.delta.content if delta.delta.content else "",
            )

            if has_finish_reason:
                for i in range(len(merged_tool_calls)):
                    merged_tool_calls[i].function = function_list[i]

                assistant_prompt_message.tool_calls = merged_tool_calls
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

        # transform usage
        usage = self._calc_response_usage(
            model, credentials, prompt_tokens, completion_tokens
        )
        final_chunk.delta.usage = usage

        yield final_chunk

    def _handle_chat_generate_response(
        self,
        model: str,
        credentials: dict,
        response: ChatCompletion,
        prompt_messages: list[PromptMessage],
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

        tool_calls: list[AssistantPromptMessage.ToolCall] = []
        if response.tool_calls is not None:
            tool_calls = [
                AssistantPromptMessage.ToolCall(
                    id=tool_call.id,
                    type=tool_call.type,
                    function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                        name=tool_call.function.name,
                        arguments=tool_call.function.arguments,
                    )
                ) for tool_call in response.tool_calls
            ]

        # transform assistant message to prompt message
        assistant_prompt_message = AssistantPromptMessage(
            content=assistant_message.content, tool_calls=tool_calls
        )

        if response.usage:
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
        else:
            prompt_tokens = 0
            completion_tokens = 0

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