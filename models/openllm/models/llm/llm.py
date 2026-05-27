from collections.abc import Generator
from typing import Optional
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    I18nObject,
    ModelPropertyKey,
    ModelType,
    ParameterRule,
    ParameterType,
)
from dify_plugin.entities.model.llm import LLMMode, LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
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
from .openllm_generate import OpenLLMGenerate, OpenLLMGenerateMessage
from .openllm_generate_errors import (
    BadRequestError,
    InsufficientAccountBalanceError,
    InternalServerError,
    InvalidAPIKeyError,
    InvalidAuthenticationError,
    RateLimitReachedError,
)


class OpenLLMLargeLanguageModel(LargeLanguageModel):
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
        Validate credentials for Baichuan model
        """
        if not credentials.get("server_url"):
            raise CredentialsValidateFailedError("Invalid server URL")
        instance = OpenLLMGenerate()
        try:
            instance.generate(
                server_url=credentials["server_url"],
                model_name=model,
                prompt_messages=[OpenLLMGenerateMessage(content="ping\nAnswer: ", role="user")],
                model_parameters={"max_tokens": 64, "temperature": 0.8, "top_p": 0.9, "top_k": 15},
                stream=False,
                user="",
                stop=[],
            )
        except InvalidAuthenticationError as e:
            raise CredentialsValidateFailedError(f"Invalid API key: {e}")

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> int:
        return self._num_tokens_from_messages(prompt_messages, tools)

    def _num_tokens_from_messages(self, messages: list[PromptMessage], tools: list[PromptMessageTool]) -> int:
        """
        Calculate num tokens for OpenLLM model
        it's a generate model, so we just join them by spe
        """
        messages = ",".join([message.content for message in messages])
        return self._get_num_tokens_by_gpt2(messages)

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
        client = OpenLLMGenerate()
        response = client.generate(
            model_name=model,
            server_url=credentials["server_url"],
            prompt_messages=[self._convert_prompt_message_to_openllm_message(message) for message in prompt_messages],
            model_parameters=model_parameters,
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

    def _convert_prompt_message_to_openllm_message(self, prompt_message: PromptMessage) -> OpenLLMGenerateMessage:
        """
        convert PromptMessage to OpenLLMGenerateMessage so that we can use OpenLLMGenerateMessage interface
        """
        if isinstance(prompt_message, UserPromptMessage):
            return OpenLLMGenerateMessage(role=OpenLLMGenerateMessage.Role.USER.value, content=prompt_message.content)
        elif isinstance(prompt_message, AssistantPromptMessage):
            return OpenLLMGenerateMessage(
                role=OpenLLMGenerateMessage.Role.ASSISTANT.value, content=prompt_message.content
            )
        else:
            raise NotImplementedError(f"Prompt message type {type(prompt_message)} is not supported")

    def _handle_chat_generate_response(
        self, model: str, prompt_messages: list[PromptMessage], credentials: dict, response: OpenLLMGenerateMessage
    ) -> LLMResult:
        usage = self._calc_response_usage(
            model=model,
            credentials=credentials,
            prompt_tokens=response.usage["prompt_tokens"],
            completion_tokens=response.usage["completion_tokens"],
        )
        return LLMResult(
            model=model,
            prompt_messages=prompt_messages,
            message=AssistantPromptMessage(content=response.content, tool_calls=[]),
            usage=usage,
        )

    def _handle_chat_generate_stream_response(
        self,
        model: str,
        prompt_messages: list[PromptMessage],
        credentials: dict,
        response: Generator[OpenLLMGenerateMessage, None, None],
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

    def get_customizable_model_schema(self, model: str, credentials: dict) -> Optional[AIModelEntity]:
        """
        used to define customizable model schema
        """
        rules = [
            ParameterRule(
                name="temperature",
                type=ParameterType.FLOAT,
                use_template="temperature",
                label=I18nObject(zh_hans="温度", en_us="Temperature"),
            ),
            ParameterRule(
                name="top_p",
                type=ParameterType.FLOAT,
                use_template="top_p",
                label=I18nObject(zh_hans="Top P", en_us="Top P"),
            ),
            ParameterRule(
                name="top_k",
                type=ParameterType.INT,
                use_template="top_k",
                min=1,
                default=1,
                label=I18nObject(zh_hans="Top K", en_us="Top K"),
            ),
            ParameterRule(
                name="max_tokens",
                type=ParameterType.INT,
                use_template="max_tokens",
                min=1,
                default=512,
                label=I18nObject(zh_hans="最大生成长度", en_us="Max Tokens"),
            ),
        ]
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_us=model),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.LLM,
            model_properties={ModelPropertyKey.MODE: LLMMode.COMPLETION.value},
            parameter_rules=rules,
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
            InvokeConnectionError: [],
            InvokeServerUnavailableError: [InternalServerError],
            InvokeRateLimitError: [RateLimitReachedError],
            InvokeAuthorizationError: [InvalidAuthenticationError, InsufficientAccountBalanceError, InvalidAPIKeyError],
            InvokeBadRequestError: [BadRequestError, KeyError],
        }
