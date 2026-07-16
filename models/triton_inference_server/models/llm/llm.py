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
from dify_plugin.entities.model.llm import LLMMode, LLMResult, LLMResultChunk, LLMResultChunkDelta, LLMUsage
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
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
from httpx import Response, post
from yarl import URL


class TritonInferenceAILargeLanguageModel(LargeLanguageModel):
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
        """
        invoke LLM

        see `core.model_runtime.model_providers.__base.large_language_model.LargeLanguageModel._invoke`
        """
        return self._generate(
            model=model,
            credentials=credentials,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user,
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        validate credentials
        """
        if "server_url" not in credentials:
            raise CredentialsValidateFailedError("server_url is required in credentials")
        try:
            self._invoke(
                model=model,
                credentials=credentials,
                prompt_messages=[UserPromptMessage(content="ping")],
                model_parameters={},
                stream=False,
            )
        except InvokeError as ex:
            raise CredentialsValidateFailedError(f"An error occurred during connection: {str(ex)}")

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> int:
        """
        get number of tokens

        cause TritonInference LLM is a customized model, we could net detect which tokenizer to use
        so we just take the GPT2 tokenizer as default
        """
        return self._get_num_tokens_by_gpt2(self._convert_prompt_message_to_text(prompt_messages))

    def _convert_prompt_message_to_text(self, message: list[PromptMessage]) -> str:
        """
        convert prompt message to text
        """
        text = ""
        for item in message:
            if isinstance(item, UserPromptMessage):
                text += f"User: {item.content}"
            elif isinstance(item, SystemPromptMessage):
                text += f"System: {item.content}"
            elif isinstance(item, AssistantPromptMessage):
                text += f"Assistant: {item.content}"
            else:
                raise NotImplementedError(f"PromptMessage type {type(item)} is not supported")
        return text

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
                name="max_tokens",
                type=ParameterType.INT,
                use_template="max_tokens",
                min=1,
                max=int(credentials.get("context_length", 2048)),
                default=min(512, int(credentials.get("context_length", 2048))),
                label=I18nObject(zh_hans="最大生成长度", en_us="Max Tokens"),
            ),
        ]
        completion_type = None
        if "completion_type" in credentials:
            if credentials["completion_type"] == "chat":
                completion_type = LLMMode.CHAT.value
            elif credentials["completion_type"] == "completion":
                completion_type = LLMMode.COMPLETION.value
            else:
                raise ValueError(f"completion_type {credentials['completion_type']} is not supported")
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_us=model),
            parameter_rules=rules,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.LLM,
            model_properties={
                ModelPropertyKey.MODE: completion_type,
                ModelPropertyKey.CONTEXT_SIZE: int(credentials.get("context_length", 2048)),
            },
        )
        return entity

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
        generate text from LLM
        """
        if "server_url" not in credentials:
            raise CredentialsValidateFailedError("server_url is required in credentials")
        if "stream" in credentials and (not bool(credentials["stream"])) and stream:
            raise ValueError(f"stream is not supported by model {model}")
        try:
            parameters = {}
            if "temperature" in model_parameters:
                parameters["temperature"] = model_parameters["temperature"]
            if "top_p" in model_parameters:
                parameters["top_p"] = model_parameters["top_p"]
            if "top_k" in model_parameters:
                parameters["top_k"] = model_parameters["top_k"]
            if "presence_penalty" in model_parameters:
                parameters["presence_penalty"] = model_parameters["presence_penalty"]
            if "frequency_penalty" in model_parameters:
                parameters["frequency_penalty"] = model_parameters["frequency_penalty"]
            response = post(
                str(URL(credentials["server_url"]) / "v2" / "models" / model / "generate"),
                json={
                    "text_input": self._convert_prompt_message_to_text(prompt_messages),
                    "max_tokens": model_parameters.get("max_tokens", 512),
                    "parameters": {"stream": False, **parameters},
                },
                timeout=(10, 120),
            )
            response.raise_for_status()
            if response.status_code != 200:
                raise InvokeBadRequestError(f"Invoke failed with status code {response.status_code}, {response.text}")
            if stream:
                return self._handle_chat_stream_response(
                    model=model, credentials=credentials, prompt_messages=prompt_messages, tools=tools, resp=response
                )
            return self._handle_chat_generate_response(
                model=model, credentials=credentials, prompt_messages=prompt_messages, tools=tools, resp=response
            )
        except Exception as ex:
            raise InvokeConnectionError(f"An error occurred during connection: {str(ex)}")

    def _handle_chat_generate_response(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool],
        resp: Response,
    ) -> LLMResult:
        """
        handle normal chat generate response
        """
        text = resp.json()["text_output"]
        usage = LLMUsage.empty_usage()
        usage.prompt_tokens = self.get_num_tokens(model, credentials, prompt_messages)
        usage.completion_tokens = self._get_num_tokens_by_gpt2(text)
        return LLMResult(
            model=model, prompt_messages=prompt_messages, message=AssistantPromptMessage(content=text), usage=usage
        )

    def _handle_chat_stream_response(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool],
        resp: Response,
    ) -> Generator:
        """
        handle normal chat generate response
        """
        text = resp.json()["text_output"]
        usage = LLMUsage.empty_usage()
        usage.prompt_tokens = self.get_num_tokens(model, credentials, prompt_messages)
        usage.completion_tokens = self._get_num_tokens_by_gpt2(text)
        yield LLMResultChunk(
            model=model,
            prompt_messages=prompt_messages,
            delta=LLMResultChunkDelta(index=0, message=AssistantPromptMessage(content=text), usage=usage),
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
            InvokeServerUnavailableError: [],
            InvokeRateLimitError: [],
            InvokeAuthorizationError: [],
            InvokeBadRequestError: [ValueError],
        }
