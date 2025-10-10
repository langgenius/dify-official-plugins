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
        # Create client
        client = self._create_client(credentials)

        # Convert prompt messages to OpenAI format
        messages = self._convert_prompt_messages(prompt_messages)

        # Prepare extra kwargs
        extra_model_kwargs = {}

        if tools:
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
            if "tool_choice" not in model_parameters:
                model_parameters["tool_choice"] = "auto"

        if stop:
            extra_model_kwargs["stop"] = stop

        # Make API call
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=stream,
            **model_parameters,
            **extra_model_kwargs,
        )

        if stream:
            return self._handle_generate_stream_response(model, credentials, response, prompt_messages)

        return self._handle_generate_response(model, credentials, response, prompt_messages)
   
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

    def _handle_generate_response(
        self,
        model: str,
        credentials: dict,
        response: ChatCompletion,
        prompt_messages: list[PromptMessage],
    ) -> LLMResult:
        """
        Handle non-streaming response

        :param model: model name
        :param credentials: credentials
        :param response: OpenAI ChatCompletion response
        :param prompt_messages: prompt messages
        :return: LLMResult
        """
        # Extract assistant message
        assistant_message = AssistantPromptMessage(content="", tool_calls=[])

        choice = response.choices[0]
        if choice.message.content:
            assistant_message.content = choice.message.content

        if choice.message.tool_calls:
            for tool_call in choice.message.tool_calls:
                assistant_message.tool_calls.append(
                    AssistantPromptMessage.ToolCall(
                        id=tool_call.id,
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=tool_call.function.name,
                            arguments=tool_call.function.arguments,
                        ),
                    )
                )

        # Calculate usage
        usage = self._calc_response_usage(
            model=model,
            credentials=credentials,
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
        )

        return LLMResult(
            model=response.model,
            prompt_messages=prompt_messages,
            message=assistant_message,
            usage=usage,
        )

    def _handle_generate_stream_response(
        self,
        model: str,
        credentials: dict,
        response: Stream[ChatCompletionChunk],
        prompt_messages: list[PromptMessage],
    ) -> Generator:
        """
        Handle streaming response

        :param model: model name
        :param credentials: credentials
        :param response: OpenAI streaming response
        :param prompt_messages: prompt messages
        :return: Generator of LLMResultChunk
        """
        from dify_plugin.entities.model.llm import LLMResultChunk, LLMResultChunkDelta

        full_content = ""
        tool_calls = []
        prompt_tokens = 0
        completion_tokens = 0

        for chunk in response:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # Handle content
            if delta.content:
                full_content += delta.content
                yield LLMResultChunk(
                    model=chunk.model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=chunk.choices[0].index,
                        message=AssistantPromptMessage(content=delta.content),
                    ),
                )

            # Handle tool calls
            if delta.tool_calls:
                for tool_call_delta in delta.tool_calls:
                    if tool_call_delta.id:
                        tool_calls.append({
                            "id": tool_call_delta.id,
                            "type": "function",
                            "function": {
                                "name": tool_call_delta.function.name if tool_call_delta.function else "",
                                "arguments": tool_call_delta.function.arguments if tool_call_delta.function else "",
                            }
                        })

            # Handle usage (comes in last chunk)
            if chunk.usage:
                prompt_tokens = chunk.usage.prompt_tokens
                completion_tokens = chunk.usage.completion_tokens

        # Send final chunk with usage
        usage = self._calc_response_usage(
            model=model,
            credentials=credentials,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        final_tool_calls = [
            AssistantPromptMessage.ToolCall(
                id=tc["id"],
                type="function",
                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                ),
            )
            for tc in tool_calls
        ] if tool_calls else []

        yield LLMResultChunk(
            model=model,
            prompt_messages=prompt_messages,
            delta=LLMResultChunkDelta(
                index=0,
                message=AssistantPromptMessage(content="", tool_calls=final_tool_calls),
                finish_reason="stop",
                usage=usage,
            ),
        )

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
