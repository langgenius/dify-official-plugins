import hashlib
import json
import logging
from collections.abc import Generator
from decimal import Decimal
from typing import Any, Optional, Union, cast

import tiktoken

from openai import OpenAI
from openai import Stream
from openai.types import Completion
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

from ..common_openai import _CommonOpenAI

from dify_plugin import LargeLanguageModel
from dify_plugin.entities import I18nObject
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    ModelType,
    PriceConfig,
)
from dify_plugin.entities.model.llm import (
    LLMMode,
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
)
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    AudioPromptMessageContent,
    DeveloperPromptMessage,
    DocumentPromptMessageContent,
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)

logger = logging.getLogger(__name__)

OPENAI_BLOCK_MODE_PROMPT = """You should always follow the instructions and output a valid {{block}} object.
The structure of the {{block}} object you can found in the instructions, use {"answer": "$your_answer"} as the default structure
if you are not sure about the structure.

<instructions>
{{instructions}}
</instructions>
"""

# thinking models compatibility for max_completion_tokens (all starting with "o" or "gpt-5")
THINKING_SERIES_PREFIXES = ("o", "gpt-5")
RESPONSES_OUTPUT_KEY = "responses_output"


def _normalize_service_tier_params(model_parameters: dict) -> None:
    """
    Remove only empty service tier values.

    OpenAI distinguishes an omitted value (auto) from ``default`` (Standard).
    See
    https://developers.openai.com/api/docs/guides/flex-processing
    """
    st = model_parameters.get("service_tier")
    if st in (None, ""):
        model_parameters.pop("service_tier", None)


def _uses_responses_api(credentials: dict) -> bool:
    return credentials.get("api_protocol") != "chat"


class OpenAILargeLanguageModel(_CommonOpenAI, LargeLanguageModel):
    """
    Model class for OpenAI large language model.
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
        model_parameters = model_parameters.copy()

        # handle fine tune remote models
        base_model = model
        if model.startswith("ft:"):
            base_model = model.split(":")[1]

        if model_parameters.pop("enable_stream", None) is False:  # noqa
            stream = False

        # get model mode
        model_mode = self.get_model_mode(base_model, credentials)

        if model_mode == LLMMode.CHAT:
            # chat model
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
        else:
            # text completion model
            return self._generate(
                model=model,
                credentials=credentials,
                prompt_messages=prompt_messages,
                model_parameters=model_parameters,
                stop=stop,
                stream=stream,
                user=user,
            )

    def _code_block_mode_wrapper(
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
        Code block mode wrapper for invoking large language model
        """
        # handle fine tune remote models
        base_model = model
        if model.startswith("ft:"):
            base_model = model.split(":")[1]

        # get model mode
        model_mode = self.get_model_mode(base_model, credentials)

        # transform response format
        if "response_format" in model_parameters and model_parameters[
            "response_format"
        ] in ["JSON", "XML"]:
            stop = stop or []
            if model_mode == LLMMode.CHAT:
                # chat model
                self._transform_chat_json_prompts(
                    model=base_model,
                    credentials=credentials,
                    prompt_messages=prompt_messages,
                    model_parameters=model_parameters,
                    tools=tools,
                    stop=stop,
                    stream=stream,
                    user=user,
                    response_format=model_parameters["response_format"],
                )
            else:
                self._transform_completion_json_prompts(
                    model=base_model,
                    credentials=credentials,
                    prompt_messages=prompt_messages,
                    model_parameters=model_parameters,
                    tools=tools,
                    stop=stop,
                    stream=stream,
                    user=user,
                    response_format=model_parameters["response_format"],
                )
            model_parameters.pop("response_format")

        return self._invoke(
            model=model,
            credentials=credentials,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
            user=user,
        )

    def _transform_chat_json_prompts(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: list[PromptMessageTool] | None = None,
        stop: list[str] | None = None,
        stream: bool = True,
        user: str | None = None,
        response_format: str = "JSON",
    ) -> None:
        """
        Transform json prompts
        """
        stop = stop or []

        if "```\n" not in stop:
            stop.append("```\n")
        if "\n```" not in stop:
            stop.append("\n```")

        # check if there is a system message
        if len(prompt_messages) > 0 and isinstance(
            prompt_messages[0], SystemPromptMessage
        ):
            assert isinstance(prompt_messages[0].content, str)
            # override the system message
            prompt_messages[0] = SystemPromptMessage(
                content=OPENAI_BLOCK_MODE_PROMPT.replace(
                    "{{instructions}}", prompt_messages[0].content
                ).replace("{{block}}", response_format)
            )
            prompt_messages.append(
                AssistantPromptMessage(content=f"\n```{response_format}\n")
            )
        else:
            # insert the system message
            prompt_messages.insert(
                0,
                SystemPromptMessage(
                    content=OPENAI_BLOCK_MODE_PROMPT.replace(
                        "{{instructions}}",
                        f"Please output a valid {response_format} object.",
                    ).replace("{{block}}", response_format)
                ),
            )
            prompt_messages.append(
                AssistantPromptMessage(content=f"\n```{response_format}")
            )

    def _transform_completion_json_prompts(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: list[PromptMessageTool] | None = None,
        stop: list[str] | None = None,
        stream: bool = True,
        user: str | None = None,
        response_format: str = "JSON",
    ) -> None:
        """
        Transform json prompts
        """
        stop = stop or []

        if "```\n" not in stop:
            stop.append("```\n")
        if "\n```" not in stop:
            stop.append("\n```")

        # override the last user message
        user_message = None
        i = None
        for i in range(len(prompt_messages) - 1, -1, -1):
            if isinstance(prompt_messages[i], UserPromptMessage):
                user_message = prompt_messages[i]
                break

        assert isinstance(i, int)

        if user_message:
            assert isinstance(prompt_messages, list)
            assert isinstance(prompt_messages[i], PromptMessage)
            content = prompt_messages[i].content
            assert isinstance(content, str)

            if content[-11:] == "Assistant: ":
                assert isinstance(user_message.content, str)
                # now we are in the chat app, remove the last assistant message
                prompt_messages[i].content = content[:-11]
                prompt_messages[i] = UserPromptMessage(
                    content=OPENAI_BLOCK_MODE_PROMPT.replace(
                        "{{instructions}}", user_message.content
                    ).replace("{{block}}", response_format)
                )
                prompt_messages[i].content += f"Assistant:\n```{response_format}\n"  # type: ignore
            else:
                assert isinstance(user_message.content, str)

                prompt_messages[i] = UserPromptMessage(
                    content=OPENAI_BLOCK_MODE_PROMPT.replace(
                        "{{instructions}}", user_message.content
                    ).replace("{{block}}", response_format)
                )

                prompt_messages[i].content += f"\n```{response_format}\n"  # type: ignore

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
        # handle fine tune remote models
        if model.startswith("ft:"):
            base_model = model.split(":")[1]
        else:
            base_model = model

        # get model mode
        model_mode = self.get_model_mode(model)

        if model_mode == LLMMode.CHAT:
            # chat model
            return self._num_tokens_from_messages(base_model, prompt_messages, tools)
        else:
            # text completion model, do not support tool calling
            content = prompt_messages[0].content
            assert isinstance(content, str)
            return self._num_tokens_from_string(base_model, content)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            # transform credentials to kwargs for model instance
            credentials_kwargs = self._to_credential_kwargs(credentials)
            client = OpenAI(**credentials_kwargs)

            # handle fine tune remote models
            base_model = model
            # fine-tuned model name likes ft:gpt-3.5-turbo-0613:personal::xxxxx
            if model.startswith("ft:"):
                base_model = model.split(":")[1]

                # check if model exists
                remote_models = self.remote_models(credentials)
                remote_model_map = {model.model: model for model in remote_models}
                if model not in remote_model_map:
                    raise CredentialsValidateFailedError(
                        f"Fine-tuned model {model} not found"
                    )

            # get model mode
            model_mode = self.get_model_mode(base_model, credentials)

            if model_mode != LLMMode.CHAT:
                client.completions.create(
                    prompt="ping",
                    model=model,
                    temperature=0,
                    max_tokens=20,
                    stream=False,
                )
            elif _uses_responses_api(credentials):
                client.responses.create(
                    model=model,
                    input="ping",
                    max_output_tokens=20,
                    store=False,
                )
            else:
                is_thinking_model = any(
                    model.startswith(prefix) for prefix in THINKING_SERIES_PREFIXES
                )
                validation_params = (
                    {"max_completion_tokens": 20, "temperature": 1}
                    if is_thinking_model
                    else {"max_tokens": 20, "temperature": 0}
                )
                client.chat.completions.create(
                    messages=[{"role": "user", "content": "ping"}],
                    model=model,
                    stream=False,
                    **validation_params,
                )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def remote_models(self, credentials: dict) -> list[AIModelEntity]:
        """
        Return remote models if credentials are provided.

        :param credentials: provider credentials
        :return:
        """
        # get predefined models
        predefined_models = self.predefined_models()
        predefined_models_map = {model.model: model for model in predefined_models}

        # transform credentials to kwargs for model instance
        credentials_kwargs = self._to_credential_kwargs(credentials)
        client = OpenAI(**credentials_kwargs)

        # get all remote models
        remote_models = client.models.list()

        fine_tune_models = [
            model for model in remote_models if model.id.startswith("ft:")
        ]

        ai_model_entities = []
        for model in fine_tune_models:
            base_model = model.id.split(":")[1]

            base_model_schema = None
            for (
                predefined_model_name,
                predefined_model,
            ) in predefined_models_map.items():
                if predefined_model_name in base_model:
                    base_model_schema = predefined_model

            if not base_model_schema:
                continue

            ai_model_entity = AIModelEntity(
                model=model.id,
                label=I18nObject(zh_hans=model.id, en_us=model.id),
                model_type=ModelType.LLM,
                features=base_model_schema.features,
                fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
                model_properties=base_model_schema.model_properties,
                parameter_rules=base_model_schema.parameter_rules,
                pricing=PriceConfig(
                    input=Decimal("0.003"),
                    output=Decimal("0.006"),
                    unit=Decimal("0.001"),
                    currency="USD",
                ),
            )

            ai_model_entities.append(ai_model_entity)

        return ai_model_entities

    def _generate(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        stop: Optional[list[str]] = None,
        stream: bool = True,
        user: Optional[str] = None,
    ) -> Union[LLMResult, Generator]:
        """
        Invoke llm completion model

        :param model: model name
        :param credentials: credentials
        :param prompt_messages: prompt messages
        :param model_parameters: model parameters
        :param stop: stop words
        :param stream: is stream response
        :param user: unique user id
        :return: full response or stream response chunk generator result
        """
        model_parameters = model_parameters.copy()

        # transform credentials to kwargs for model instance
        credentials_kwargs = self._to_credential_kwargs(credentials)

        # init model client
        client = OpenAI(**credentials_kwargs)

        extra_model_kwargs = {}

        if stop:
            extra_model_kwargs["stop"] = stop

        if user:
            extra_model_kwargs["user"] = user

        if stream:
            extra_model_kwargs["stream_options"] = {"include_usage": True}

        _normalize_service_tier_params(model_parameters)

        # text completion model
        assert isinstance(prompt_messages[0].content, str)
        completion_params = model_parameters.copy()
        if any(model.startswith(prefix) for prefix in THINKING_SERIES_PREFIXES):
            if "max_tokens" in completion_params:
                completion_params["max_completion_tokens"] = completion_params.pop("max_tokens")

        response = client.completions.create(
            prompt=prompt_messages[0].content,
            model=model,
            stream=stream,
            **completion_params,
            **extra_model_kwargs,
        )

        if stream:
            assert isinstance(response, Stream)
            return self._handle_generate_stream_response(
                model, credentials, response, prompt_messages
            )

        assert isinstance(response, Completion)
        return self._handle_generate_response(
            model, credentials, response, prompt_messages
        )

    def _handle_generate_response(
        self,
        model: str,
        credentials: dict,
        response: Completion,
        prompt_messages: list[PromptMessage],
    ) -> LLMResult:
        """
        Handle llm completion response

        :param model: model name
        :param credentials: model credentials
        :param response: response
        :param prompt_messages: prompt messages
        :return: llm result
        """
        assistant_text = response.choices[0].text

        # transform assistant message to prompt message
        assistant_prompt_message = AssistantPromptMessage(content=assistant_text)

        # calculate num tokens
        if response.usage:
            # transform usage
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
        else:
            # calculate num tokens
            assert isinstance(prompt_messages[0].content, str)
            prompt_tokens = self._num_tokens_from_string(
                model, prompt_messages[0].content
            )
            completion_tokens = self._num_tokens_from_string(model, assistant_text)

        # transform usage
        usage = self._calc_response_usage(
            model, credentials, prompt_tokens, completion_tokens
        )

        # transform response
        result = LLMResult(
            model=response.model,
            prompt_messages=prompt_messages,
            message=assistant_prompt_message,
            usage=usage,
            system_fingerprint=response.system_fingerprint,
        )

        return result

    def _handle_generate_stream_response(
        self,
        model: str,
        credentials: dict,
        response: Stream[Completion],
        prompt_messages: list[PromptMessage],
    ) -> Generator:
        """
        Handle llm completion stream response

        :param model: model name
        :param credentials: model credentials
        :param response: response
        :param prompt_messages: prompt messages
        :return: llm response chunk generator result
        """
        full_text = ""
        prompt_tokens = 0
        completion_tokens = 0

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

            if delta.finish_reason is None and (delta.text is None or delta.text == ""):
                continue

            # transform assistant message to prompt message
            text = delta.text if delta.text else ""
            assistant_prompt_message = AssistantPromptMessage(content=text)

            full_text += text

            if delta.finish_reason is not None:
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
            assert isinstance(prompt_messages[0].content, str)
            prompt_tokens = self._num_tokens_from_string(
                model, prompt_messages[0].content
            )

        if not completion_tokens:
            completion_tokens = self._num_tokens_from_string(model, full_text)

        # transform usage
        usage = self._calc_response_usage(
            model, credentials, prompt_tokens, completion_tokens
        )

        final_chunk.delta.usage = usage

        yield final_chunk

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
        model_parameters = model_parameters.copy()

        # transform credentials to kwargs for model instance
        credentials_kwargs = self._to_credential_kwargs(credentials)

        # init model client
        client = OpenAI(**credentials_kwargs)

        _normalize_service_tier_params(model_parameters)

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

        extra_model_kwargs = {}

        if tools:
            # Build new "tools" payload per 2024-06 API spec
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

            # default behaviour is "auto" if tools present – keep current behaviour
            # but allow the caller to override via model_parameters["tool_choice"]

            if "tool_choice" not in model_parameters:
                model_parameters["tool_choice"] = "auto"

        else:
            pass

        if stop:
            extra_model_kwargs["stop"] = stop

        if user:
            extra_model_kwargs["user"] = user

        if stream:
            extra_model_kwargs["stream_options"] = {"include_usage": True}

        # clear illegal prompt messages
        prompt_messages = self._clear_illegal_prompt_messages(model, prompt_messages)

        if _uses_responses_api(credentials):
            if stream:
                return self._chat_generate_responses_api_stream(
                    model=model,
                    credentials=credentials,
                    prompt_messages=prompt_messages,
                    model_parameters=model_parameters,
                    tools=tools,
                    client=client,
                    user=user,
                    stop=stop,
                )
            block_result = self._chat_generate_responses_api(
                model=model,
                credentials=credentials,
                prompt_messages=prompt_messages,
                model_parameters=model_parameters,
                tools=tools,
                client=client,
                user=user,
                stop=stop,
            )
        else:
            # chat model
            messages: Any = [self._convert_prompt_message_to_dict(m) for m in prompt_messages]
            # thinking models require max_completion_tokens instead of max_tokens
            chat_params = model_parameters.copy()
            if any(model.startswith(prefix) for prefix in THINKING_SERIES_PREFIXES):
                if "max_tokens" in chat_params:
                    chat_params["max_completion_tokens"] = chat_params.pop("max_tokens")
            response = client.chat.completions.create(
                messages=messages,
                model=model,
                stream=stream,
                **chat_params,
                **extra_model_kwargs,
            )

            if stream:
                logger.info(f"OpenAI API Response - Stream response initiated for model: {model}")
                return self._handle_chat_generate_stream_response(model, credentials, response, prompt_messages, tools)

            block_result = self._handle_chat_generate_response(model, credentials, response, prompt_messages, tools)

        return block_result

    def _build_responses_api_params(
        self,
        model_parameters: dict,
        user: Optional[str] = None,
    ) -> dict:
        """
        Convert model_parameters to Responses API compatible params.
        Handles parameter renaming and restructuring.
        """
        params = model_parameters.copy()

        for name in ("presence_penalty", "frequency_penalty"):
            value = params.pop(name, None)
            if value not in (None, 0, 0.0):
                raise InvokeBadRequestError(
                    f"{name} is not supported by the Responses API; "
                    "select Chat Completions to use it."
                )

        if params.pop("seed", None) is not None:
            raise InvokeBadRequestError(
                "seed is not supported by the Responses API; " "select Chat Completions to use it."
            )

        # max_tokens / max_completion_tokens -> max_output_tokens
        if "max_tokens" in params:
            params["max_output_tokens"] = params.pop("max_tokens")
        if "max_completion_tokens" in params:
            params["max_output_tokens"] = params.pop("max_completion_tokens")

        # reasoning_effort -> reasoning.effort
        reasoning_effort = params.pop("reasoning_effort", None)
        if reasoning_effort not in (None, ""):
            params["reasoning"] = {"effort": reasoning_effort}

        # response_format -> text.format (Responses API uses different format)
        # https://developers.openai.com/api/docs/guides/structured-outputs
        response_format = params.pop("response_format", None)
        if response_format:
            if isinstance(response_format, dict):
                if response_format.get("type") == "json_schema":
                    json_schema = response_format.get("json_schema", response_format)
                    if not isinstance(json_schema, dict):
                        raise InvokeBadRequestError("JSON Schema must be an object")
                    if "schema" in json_schema:
                        schema_obj = json_schema
                    else:
                        schema_obj = {"schema": json_schema}

                    text_format = {
                        "type": "json_schema",
                        "name": schema_obj.get("name", "response"),
                        "schema": schema_obj["schema"],
                    }
                    for field in ("description", "strict"):
                        if field in schema_obj:
                            text_format[field] = schema_obj[field]
                    params["text"] = {"format": text_format}
                else:
                    params["text"] = {"format": {"type": response_format.get("type", "text")}}
            elif isinstance(response_format, str):
                params["text"] = {"format": {"type": response_format}}

        params.pop("json_schema", None)

        # verbosity -> text.verbosity
        verbosity = params.pop("verbosity", None)
        if verbosity is not None:
            params.setdefault("text", {})["verbosity"] = verbosity

        tool_choice = params.get("tool_choice")
        if isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
            function = tool_choice.get("function")
            if isinstance(function, dict) and function.get("name"):
                params["tool_choice"] = {
                    "type": "function",
                    "name": function["name"],
                }

        legacy_user = params.pop("user", None)
        end_user = user or legacy_user
        if end_user:
            end_user_hash = hashlib.sha256(end_user.encode()).hexdigest()
            params.setdefault("safety_identifier", end_user_hash)
            params.setdefault("prompt_cache_key", end_user_hash)

        if params.get("store") is None:
            params["store"] = False
        if params["store"] is False:
            include = list(params.get("include") or [])
            if "reasoning.encrypted_content" not in include:
                include.append("reasoning.encrypted_content")
            params["include"] = include

        return params

    @staticmethod
    def _convert_responses_content(content_items: list[Any]) -> list[dict]:
        content: list[dict] = []
        for item in content_items:
            if item.type == PromptMessageContentType.TEXT:
                content.append(
                    {
                        "type": "input_text",
                        "text": cast(TextPromptMessageContent, item).data,
                    }
                )
            elif item.type == PromptMessageContentType.IMAGE:
                image = cast(ImagePromptMessageContent, item)
                if not image.url and not image.base64_data:
                    raise InvokeBadRequestError("Image input must include a URL or base64 data")
                image_part = {
                    "type": "input_image",
                    "image_url": image.data,
                }
                if "detail" in image.model_fields_set:
                    image_part["detail"] = image.detail.value
                content.append(image_part)
            elif item.type == PromptMessageContentType.DOCUMENT:
                document = cast(DocumentPromptMessageContent, item)
                file_part: dict[str, Any] = {"type": "input_file"}
                if document.url:
                    file_part["file_url"] = document.url
                elif document.base64_data:
                    suffix = document.format.lstrip(".")
                    file_part["filename"] = document.filename or (
                        f"document.{suffix}" if suffix else "document"
                    )
                    file_part["file_data"] = document.data
                else:
                    raise InvokeBadRequestError("Document input must include a URL or base64 data")
                content.append(file_part)
            elif item.type in (PromptMessageContentType.AUDIO, PromptMessageContentType.VIDEO):
                raise InvokeBadRequestError(
                    f"{item.type.value} input is not supported by the Responses API; "
                    "select Chat Completions for this request."
                )
            else:
                raise InvokeBadRequestError(f"Unsupported Responses API content type: {item.type}")
        return content

    def _convert_prompt_messages_to_responses_input(
        self,
        prompt_messages: list[PromptMessage],
    ) -> list[dict]:
        """Convert prompt messages to typed Responses API input items."""
        input_items: list[dict] = []
        for message in prompt_messages:
            if isinstance(
                message,
                (SystemPromptMessage, DeveloperPromptMessage, UserPromptMessage),
            ):
                if isinstance(message, SystemPromptMessage):
                    role = "system"
                elif isinstance(message, DeveloperPromptMessage):
                    role = "developer"
                else:
                    role = "user"

                if isinstance(message.content, str):
                    content: Any = message.content
                else:
                    content = self._convert_responses_content(message.content or [])
                if content not in (None, "", []):
                    input_items.append(
                        {
                            "type": "message",
                            "role": role,
                            "content": content,
                        }
                    )
            elif isinstance(message, AssistantPromptMessage):
                opaque_body = message.opaque_body
                if isinstance(opaque_body, dict):
                    output_items = opaque_body.get(RESPONSES_OUTPUT_KEY)
                    if isinstance(output_items, list) and all(
                        isinstance(item, dict) for item in output_items
                    ):
                        input_items.extend(item.copy() for item in output_items)
                        continue

                if isinstance(message.content, str):
                    assistant_content: Any = message.content
                else:
                    assistant_content = self._convert_responses_content(message.content or [])
                if assistant_content not in (None, "", []):
                    input_items.append(
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": assistant_content,
                        }
                    )
                for tool_call in message.tool_calls:
                    input_items.append(
                        {
                            "type": "function_call",
                            "call_id": tool_call.id,
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments,
                        }
                    )
            elif isinstance(message, ToolPromptMessage):
                if isinstance(message.content, str):
                    output: Any = message.content
                elif isinstance(message.content, list):
                    output = self._convert_responses_content(message.content) or ""
                else:
                    output = ""
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.tool_call_id,
                        "output": output,
                    }
                )
            else:
                raise InvokeBadRequestError(
                    f"Unsupported Responses API prompt message: {type(message).__name__}"
                )
        return input_items

    def _build_responses_api_tools(
        self, tools: Optional[list[PromptMessageTool]]
    ) -> Optional[list[dict]]:
        """Convert PromptMessageTool list to Responses API tool format."""
        if not tools:
            return None
        return [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "strict": False,
            }
            for tool in tools
        ]

    @staticmethod
    def _response_field(value: Any, field: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(field, default)
        return getattr(value, field, default)

    @classmethod
    def _to_json_value(cls, value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, dict):
            return {key: cls._to_json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._to_json_value(item) for item in value]
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json", exclude_none=True)
        if hasattr(value, "__dict__"):
            return {
                key: cls._to_json_value(item)
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        raise TypeError(f"Cannot serialize Responses API output item: {type(value).__name__}")

    @classmethod
    def _responses_opaque_body(cls, response: Any) -> dict[str, Any]:
        output_items = cls._to_json_value(cls._response_field(response, "output", []))
        return {RESPONSES_OUTPUT_KEY: output_items}

    @classmethod
    def _extract_responses_text(cls, response: Any) -> str:
        parts: list[str] = []
        for item in cls._response_field(response, "output", []) or []:
            if cls._response_field(item, "type") != "message":
                continue
            for content in cls._response_field(item, "content", []) or []:
                content_type = cls._response_field(content, "type")
                if content_type == "output_text":
                    parts.append(cls._response_field(content, "text", "") or "")
                elif content_type == "refusal":
                    parts.append(cls._response_field(content, "refusal", "") or "")
        if parts:
            return "".join(parts)
        return cls._response_field(response, "output_text", "") or ""

    @classmethod
    def _extract_responses_tool_calls(cls, response: Any) -> list[AssistantPromptMessage.ToolCall]:
        tool_calls: list[AssistantPromptMessage.ToolCall] = []
        for item in cls._response_field(response, "output", []) or []:
            if cls._response_field(item, "type") != "function_call":
                continue
            if cls._response_field(item, "status") not in (None, "completed"):
                continue
            tool_calls.append(
                AssistantPromptMessage.ToolCall(
                    id=cls._response_field(item, "call_id", ""),
                    type="function",
                    function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                        name=cls._response_field(item, "name", ""),
                        arguments=cls._response_field(item, "arguments", ""),
                    ),
                )
            )
        return tool_calls

    @classmethod
    def _raise_for_responses_status(cls, response: Any, *, allow_incomplete: bool = False) -> None:
        status = cls._response_field(response, "status")
        error = cls._response_field(response, "error")
        if error is not None or status == "failed":
            cls._raise_responses_error(error)
        if status == "incomplete" and not allow_incomplete:
            details = cls._response_field(response, "incomplete_details")
            reason = cls._response_field(details, "reason", "unknown")
            raise InvokeBadRequestError(f"OpenAI response incomplete: {reason}")
        if status in ("cancelled", "queued", "in_progress"):
            raise InvokeServerUnavailableError(f"Unexpected OpenAI response status: {status}")
        if isinstance(status, str) and status not in ("completed", "incomplete"):
            raise InvokeServerUnavailableError(f"Unknown OpenAI response status: {status}")

    @classmethod
    def _raise_responses_error(cls, error: Any) -> None:
        code = cls._response_field(error, "code", "response_failed")
        message = cls._response_field(error, "message", "OpenAI response failed")
        description = f"OpenAI {code}: {message}"
        if code == "rate_limit_exceeded":
            raise InvokeRateLimitError(description)
        if code in ("server_error", "vector_store_timeout", "response_failed"):
            raise InvokeServerUnavailableError(description)
        raise InvokeBadRequestError(description)

    @staticmethod
    def _truncate_at_stop(text: str, stop: Optional[list[str]]) -> str:
        positions = [text.find(token) for token in stop or [] if token]
        positions = [position for position in positions if position >= 0]
        return text[: min(positions)] if positions else text

    def _chat_generate_responses_api(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: Optional[list[PromptMessageTool]],
        client: OpenAI,
        user: Optional[str] = None,
        stop: Optional[list[str]] = None,
    ) -> LLMResult:
        """Invoke a model using the non-streaming Responses API."""
        response_params = self._build_responses_api_params(model_parameters, user)

        input_items = self._convert_prompt_messages_to_responses_input(prompt_messages)
        api_tools = self._build_responses_api_tools(tools)
        if api_tools:
            response_params["tools"] = api_tools
            if "tool_choice" not in response_params:
                response_params["tool_choice"] = "auto"

        resp_obj = client.responses.create(
            model=model,
            input=input_items,
            **response_params,
        )

        self._raise_for_responses_status(resp_obj, allow_incomplete=True)
        response_status = self._response_field(resp_obj, "status")
        raw_text_content = self._extract_responses_text(resp_obj)
        text_content = self._truncate_at_stop(raw_text_content, stop)
        tool_calls = (
            self._extract_responses_tool_calls(resp_obj)
            if response_status == "completed" and text_content == raw_text_content
            else []
        )
        opaque_body = (
            self._responses_opaque_body(resp_obj)
            if response_status in ("completed", "incomplete") and text_content == raw_text_content
            else None
        )

        assistant_prompt_message = AssistantPromptMessage(
            content=text_content,
            tool_calls=tool_calls,
            opaque_body=opaque_body,
        )

        response_usage = self._response_field(resp_obj, "usage")
        if response_usage is not None:
            prompt_tokens = self._response_field(response_usage, "input_tokens", 0)
            completion_tokens = self._response_field(response_usage, "output_tokens", 0)
        else:
            prompt_tokens = self._num_tokens_from_messages(model, prompt_messages, tools)
            completion_input = raw_text_content + "".join(
                tool_call.function.arguments for tool_call in tool_calls
            )
            completion_tokens = self._num_tokens_from_string(model, completion_input)
        usage = self._calc_response_usage(
            model=model,
            credentials=credentials,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        return LLMResult(
            model=self._response_field(resp_obj, "model", model),
            prompt_messages=prompt_messages,
            message=assistant_prompt_message,
            usage=usage,
            system_fingerprint=None,
        )

    def _chat_generate_responses_api_stream(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        model_parameters: dict,
        tools: Optional[list[PromptMessageTool]],
        client: OpenAI,
        user: Optional[str] = None,
        stop: Optional[list[str]] = None,
    ) -> Generator:
        """Invoke a model using the streaming Responses API."""
        response_params = self._build_responses_api_params(model_parameters, user)

        input_items = self._convert_prompt_messages_to_responses_input(prompt_messages)
        api_tools = self._build_responses_api_tools(tools)
        if api_tools:
            response_params["tools"] = api_tools
            if "tool_choice" not in response_params:
                response_params["tool_choice"] = "auto"

        stream = client.responses.create(
            model=model,
            input=input_items,
            stream=True,
            **response_params,
        )

        stop_sequences = [token for token in stop or [] if token]
        max_stop_length = max((len(token) for token in stop_sequences), default=0)
        pending_text = ""
        generated_text = ""
        stopped = False
        terminal_response = None
        terminal_finish_reason = "stop"

        for event in stream:
            event_type = self._response_field(event, "type")
            logger.debug("Responses API stream event: %s", event_type)

            if event_type in ("response.output_text.delta", "response.refusal.delta"):
                delta_text = self._response_field(event, "delta", "") or ""
                if delta_text:
                    generated_text += delta_text
                    visible_text = ""
                    if not stopped and not stop_sequences:
                        visible_text = delta_text
                    elif not stopped:
                        pending_text += delta_text
                        stopped_text = self._truncate_at_stop(
                            pending_text,
                            stop_sequences,
                        )
                        if len(stopped_text) < len(pending_text):
                            visible_text = stopped_text
                            pending_text = ""
                            stopped = True
                        else:
                            emit_length = max(0, len(pending_text) - max_stop_length + 1)
                            visible_text = pending_text[:emit_length]
                            pending_text = pending_text[emit_length:]

                    if visible_text:
                        yield LLMResultChunk(
                            model=model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=0,
                                message=AssistantPromptMessage(content=visible_text),
                            ),
                        )

            elif event_type == "response.completed":
                terminal_response = self._response_field(event, "response")
                self._raise_for_responses_status(terminal_response)

            elif event_type == "response.incomplete":
                terminal_response = self._response_field(event, "response")
                self._raise_for_responses_status(
                    terminal_response,
                    allow_incomplete=True,
                )
                details = self._response_field(
                    terminal_response,
                    "incomplete_details",
                )
                reason = self._response_field(details, "reason")
                terminal_finish_reason = {
                    "max_output_tokens": "length",
                    "content_filter": "content_filter",
                }.get(reason, "incomplete")

            elif event_type == "response.failed":
                failed_response = self._response_field(event, "response")
                self._raise_for_responses_status(failed_response)
                raise InvokeServerUnavailableError("OpenAI response failed")

            elif event_type == "error":
                self._raise_responses_error(event)

            else:
                logger.debug("Ignoring Responses API stream event: %s", event_type)

        if terminal_response is None:
            raise InvokeConnectionError("OpenAI Responses stream ended without a terminal event")

        final_model = self._response_field(terminal_response, "model", model)
        if generated_text:
            if pending_text and not stopped:
                yield LLMResultChunk(
                    model=final_model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(content=pending_text),
                    ),
                )
        else:
            generated_text = self._extract_responses_text(terminal_response)
            visible_text = self._truncate_at_stop(generated_text, stop_sequences)
            stopped = visible_text != generated_text
            if visible_text:
                yield LLMResultChunk(
                    model=final_model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(content=visible_text),
                    ),
                )

        response_usage = self._response_field(terminal_response, "usage")
        tool_calls: list[AssistantPromptMessage.ToolCall] = []
        opaque_body = None
        terminal_status = self._response_field(terminal_response, "status")
        if terminal_status in ("completed", "incomplete") and not stopped:
            opaque_body = self._responses_opaque_body(terminal_response)
        if terminal_status == "completed" and not stopped:
            tool_calls = self._extract_responses_tool_calls(terminal_response)
            if tool_calls:
                terminal_finish_reason = "tool_calls"
        if stopped:
            terminal_finish_reason = "stop"

        if response_usage is not None:
            prompt_tokens = self._response_field(response_usage, "input_tokens", 0)
            completion_tokens = self._response_field(response_usage, "output_tokens", 0)
        else:
            prompt_tokens = self._num_tokens_from_messages(model, prompt_messages, tools)
            completion_input = generated_text + "".join(
                tool_call.function.arguments for tool_call in tool_calls
            )
            completion_tokens = self._num_tokens_from_string(model, completion_input)

        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)
        yield LLMResultChunk(
            model=final_model,
            prompt_messages=prompt_messages,
            delta=LLMResultChunkDelta(
                index=0,
                message=AssistantPromptMessage(
                    content="",
                    tool_calls=tool_calls,
                    opaque_body=opaque_body,
                ),
                finish_reason=terminal_finish_reason,
                usage=usage,
            ),
        )

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

        # Prefer new tool_calls field, fallback to deprecated function_call
        assistant_message_tool_calls = assistant_message.tool_calls
        tool_calls: list[AssistantPromptMessage.ToolCall] = []
        if assistant_message_tool_calls:
            tool_calls = self._extract_response_tool_calls(assistant_message_tool_calls)  # type: ignore
        elif assistant_message.function_call:
            function_call = self._extract_response_function_call(assistant_message.function_call)
            if function_call:
                tool_calls = [function_call]

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
        aggregated_tool_calls: dict[int, ChoiceDeltaToolCall] = {}
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
            # to fix issue #12215 yi model has special case for ligthing
            # FIXME drop the case when yi model is updated
            if model.startswith("yi-"):
                if isinstance(delta.finish_reason, str):
                    # doc: https://platform.lingyiwanwu.com/docs/api-reference
                    has_finish_reason = delta.finish_reason.startswith(("length", "stop", "content_filter"))

            if (
                not has_finish_reason
                and (delta.delta.content is None or delta.delta.content == "")
                and delta.delta.tool_calls is None
                and delta.delta.function_call is None
            ):
                continue

            assistant_message_tool_calls = delta.delta.tool_calls
            assistant_message_function_call = delta.delta.function_call

            # extract tool calls from response (new preferred path)
            if assistant_message_tool_calls:
                tool_calls = self._extract_response_tool_calls(assistant_message_tool_calls)  # type: ignore
            else:
                # legacy streaming via function_call
                if delta_assistant_message_function_call_storage is not None:
                    if assistant_message_function_call:
                        # message continues
                        assert isinstance(delta_assistant_message_function_call_storage.arguments, str)
                        assert isinstance(assistant_message_function_call.arguments, str)
                        delta_assistant_message_function_call_storage.arguments += assistant_message_function_call.arguments
                        continue
                    else:
                        assistant_message_function_call = delta_assistant_message_function_call_storage
                        delta_assistant_message_function_call_storage = None
                else:
                    if assistant_message_function_call:
                        # start of legacy stream
                        delta_assistant_message_function_call_storage = assistant_message_function_call
                        if delta_assistant_message_function_call_storage.arguments is None:
                            delta_assistant_message_function_call_storage.arguments = ""
                        if not has_finish_reason:
                            continue

                function_call = self._extract_response_function_call(assistant_message_function_call)
                tool_calls = [function_call] if function_call else []

            if tool_calls:
                final_tool_calls.extend(tool_calls)


            # STATEFUL AGGREGATION OF TOOL CALLS
            if assistant_message_tool_calls:
                for tool_call_chunk in assistant_message_tool_calls:
                    # new tool
                    if tool_call_chunk.id and tool_call_chunk.index not in aggregated_tool_calls:
                        aggregated_tool_calls[tool_call_chunk.index] = tool_call_chunk
                    # existing tool
                    elif tool_call_chunk.index in aggregated_tool_calls:
                        existing_call = aggregated_tool_calls[tool_call_chunk.index]
                        if tool_call_chunk.id:
                            existing_call.id = tool_call_chunk.id
                        if tool_call_chunk.type:
                            existing_call.type = tool_call_chunk.type
                        if tool_call_chunk.function:
                            if tool_call_chunk.function.name:
                                existing_call.function.name = tool_call_chunk.function.name
                            if tool_call_chunk.function.arguments:
                                existing_call.function.arguments += tool_call_chunk.function.arguments

            if has_finish_reason and delta.finish_reason == "tool_calls":
                # all tool calls are finished, yield them
                tool_calls = self._extract_response_tool_calls(list(aggregated_tool_calls.values()))
                final_tool_calls.extend(tool_calls)
                assistant_prompt_message = AssistantPromptMessage(
                    content="",
                    tool_calls=tool_calls
                )

                yield LLMResultChunk(
                    model=chunk.model,
                    prompt_messages=prompt_messages,
                    system_fingerprint=chunk.system_fingerprint,
                    delta=LLMResultChunkDelta(
                        index=delta.index,
                        message=assistant_prompt_message,
                        finish_reason="tool_calls" # forward the finish reason
                    )
                )
                continue

            # transform assistant message to prompt message
            assistant_prompt_message = AssistantPromptMessage(
                content=delta.delta.content if delta.delta.content else "",
                tool_calls=[],
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
                if response_tool_call.function:
                    function = AssistantPromptMessage.ToolCall.ToolCallFunction(
                        name=response_tool_call.function.name or "",
                        arguments=response_tool_call.function.arguments or "",
                    )

                    tool_call = AssistantPromptMessage.ToolCall(
                        id=response_tool_call.id or "",
                        type=response_tool_call.type or "",
                        function=function,
                    )
                    tool_calls.append(tool_call)

        return tool_calls

    def _extract_response_function_call(
        self, response_function_call: Optional[FunctionCall | ChoiceDeltaFunctionCall]
    ) -> Optional[AssistantPromptMessage.ToolCall]:
        """
        Extract function call from response

        :param response_function_call: response function call
        :return: tool call
        """
        tool_call = None
        if response_function_call:
            # Avoid isinstance with possibly generic typing classes; use duck-typing instead
            if not hasattr(response_function_call, "name"):
                return None

            function = AssistantPromptMessage.ToolCall.ToolCallFunction(
                name=response_function_call.name or "",
                arguments=response_function_call.arguments or "",
            )

            tool_call = AssistantPromptMessage.ToolCall(
                id=response_function_call.name or "", type="function", function=function
            )

        return tool_call

    def _clear_illegal_prompt_messages(
        self, model: str, prompt_messages: list[PromptMessage]
    ) -> list[PromptMessage]:
        """
        Clear illegal prompt messages for OpenAI API

        :param model: model name
        :param prompt_messages: prompt messages
        :return: cleaned prompt messages
        """
        checklist = ["gpt-4-turbo", "gpt-4-turbo-2024-04-09"]

        if model in checklist:
            # count how many user messages are there
            user_message_count = len(
                [m for m in prompt_messages if isinstance(m, UserPromptMessage)]
            )
            if user_message_count > 1:
                for prompt_message in prompt_messages:
                    if isinstance(prompt_message, UserPromptMessage):
                        if isinstance(prompt_message.content, list):
                            prompt_message.content = "\n".join(
                                [
                                    item.data
                                    if item.type == PromptMessageContentType.TEXT
                                    else "[IMAGE]"
                                    if item.type == PromptMessageContentType.IMAGE
                                    else ""
                                    for item in prompt_message.content
                                ]
                            )

        return prompt_messages

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
                    elif isinstance(message_content, AudioPromptMessageContent):
                        data_split = message_content.data.split(";base64,")
                        base64_data = data_split[1]
                        sub_message_dict = {
                            "type": "input_audio",
                            "input_audio": {
                                "data": base64_data,
                                "format": message_content.format,
                            },
                        }
                        sub_messages.append(sub_message_dict)

                message_dict = {"role": "user", "content": sub_messages}
        elif isinstance(message, AssistantPromptMessage):
            message = cast(AssistantPromptMessage, message)
            message_dict = {"role": "assistant", "content": message.content}

            # If assistant wants to call tools, attach tool_calls per new spec
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
        elif isinstance(message, SystemPromptMessage):
            message = cast(SystemPromptMessage, message)
            message_dict = {"role": "system", "content": message.content}
        elif isinstance(message, DeveloperPromptMessage):
            message_dict = {"role": "developer", "content": message.content}
        elif isinstance(message, ToolPromptMessage):
            message = cast(ToolPromptMessage, message)
            message_dict = {
                "role": "tool",
                "content": message.content,
                "tool_call_id": message.tool_call_id,
            }
        else:
            raise ValueError(f"Got unknown type {message}")

        if message.name and message_dict.get("role") != "tool":
            message_dict["name"] = message.name

        return message_dict

    def _num_tokens_from_string(
        self, model: str, text: str, tools: Optional[list[PromptMessageTool]] = None
    ) -> int:
        """
        Calculate num tokens for text completion model with tiktoken package.

        :param model: model name
        :param text: prompt text
        :param tools: tools for tool calling
        :return: number of tokens
        """
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")

        num_tokens = len(encoding.encode(text))

        if tools:
            num_tokens += self._num_tokens_for_tools(encoding, tools)

        return num_tokens

    def _num_tokens_from_messages(
        self,
        model: str,
        messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        """Calculate num tokens for gpt-3.5-turbo and gpt-4 with tiktoken package.

        Official documentation: https://github.com/openai/openai-cookbook/blob/
        main/examples/How_to_format_inputs_to_ChatGPT_models.ipynb"""
        if model.startswith("ft:"):
            model = model.split(":")[1]

        # Currently, we can use gpt4o to calculate chatgpt-4o-latest's token.
        if model == "chatgpt-4o-latest" or model.startswith(("o1", "o3", "o4", "gpt-4.1", "gpt-4.5", "gpt-5")):
            model = "gpt-4o"

        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            logger.warning("Warning: model not found. Using cl100k_base encoding.")
            encoding_name = "cl100k_base"
            encoding = tiktoken.get_encoding(encoding_name)

        if model.startswith("gpt-3.5-turbo-0301"):
            # every message follows <im_start>{role/name}\n{content}<im_end>\n
            tokens_per_message = 4
            # if there's a name, the role is omitted
            tokens_per_name = -1
        elif (
            model.startswith("gpt-3.5-turbo")
            or model.startswith("gpt-4")
            or model.startswith(("o1", "o3", "o4"))
            or model.startswith("gpt-5")
        ):
            tokens_per_message = 3
            tokens_per_name = 1
        else:
            raise NotImplementedError(
                f"get_num_tokens_from_messages() is not presently implemented "
                f"for model {model}."
                "See https://platform.openai.com/docs/advanced-usage/managing-tokens for for "
                "information on how messages are converted to tokens."
            )
        num_tokens = 0
        messages_dict = [self._convert_prompt_message_to_dict(m) for m in messages]
        for message in messages_dict:
            num_tokens += tokens_per_message
            for key, value in message.items():
                # Cast str(value) in case the message value is not a string
                # This occurs with function messages
                # TODO: The current token calculation method for the image type is not implemented,
                #  which need to download the image and then get the resolution for calculation,
                #  and will increase the request delay
                if isinstance(value, list):
                    text = ""
                    for item in value:
                        if isinstance(item, dict) and item["type"] == "text":
                            text += item["text"]

                    value = text

                if key == "tool_calls":
                    for tool_call in value:
                        for t_key, t_value in tool_call.items():  # type: ignore
                            num_tokens += len(encoding.encode(t_key))
                            if t_key == "function":
                                for f_key, f_value in t_value.items():
                                    num_tokens += len(encoding.encode(f_key))
                                    num_tokens += len(encoding.encode(f_value))
                            else:
                                num_tokens += len(encoding.encode(t_key))
                                num_tokens += len(encoding.encode(t_value))
                else:
                    num_tokens += len(encoding.encode(str(value)))

                if key == "name":
                    num_tokens += tokens_per_name

        # every reply is primed with <im_start>assistant
        num_tokens += 3

        if tools:
            num_tokens += self._num_tokens_for_tools(encoding, tools)

        return num_tokens

    def _num_tokens_for_tools(
        self, encoding: tiktoken.Encoding, tools: list[PromptMessageTool]
    ) -> int:
        """
        Calculate num tokens for tool calling with tiktoken package.

        :param encoding: encoding
        :param tools: tools for tool calling
        :return: number of tokens
        """
        num_tokens = 0
        for tool in tools:
            num_tokens += len(encoding.encode("type"))
            num_tokens += len(encoding.encode("function"))

            # calculate num tokens for function object
            num_tokens += len(encoding.encode("name"))
            num_tokens += len(encoding.encode(tool.name))
            num_tokens += len(encoding.encode("description"))
            num_tokens += len(encoding.encode(tool.description))
            parameters = tool.parameters
            num_tokens += len(encoding.encode("parameters"))
            if "title" in parameters:
                num_tokens += len(encoding.encode("title"))
                num_tokens += len(encoding.encode(parameters.get("title")))  # type: ignore
            num_tokens += len(encoding.encode("type"))
            num_tokens += len(encoding.encode(parameters.get("type")))  # type: ignore
            if "properties" in parameters:
                num_tokens += len(encoding.encode("properties"))
                for key, value in parameters.get("properties").items():  # type: ignore
                    num_tokens += len(encoding.encode(key))
                    for field_key, field_value in value.items():
                        num_tokens += len(encoding.encode(field_key))
                        if field_key == "enum":
                            for enum_field in field_value:
                                num_tokens += 3
                                num_tokens += len(encoding.encode(enum_field))
                        else:
                            num_tokens += len(encoding.encode(field_key))
                            num_tokens += len(encoding.encode(str(field_value)))
            if "required" in parameters:
                num_tokens += len(encoding.encode("required"))
                for required_field in parameters["required"]:
                    num_tokens += 3
                    num_tokens += len(encoding.encode(required_field))

        return num_tokens

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> AIModelEntity:
        """
        OpenAI supports fine-tuning of their models. This method returns the schema of the base model
        but renamed to the fine-tuned model name.

        :param model: model name
        :param credentials: credentials

        :return: model schema
        """
        if not model.startswith("ft:"):
            base_model = model
        else:
            # get base_model
            base_model = model.split(":")[1]

        # get model schema
        models = self.predefined_models()
        model_map = {model.model: model for model in models}
        if base_model not in model_map:
            raise ValueError(f"Base model {base_model} not found")

        base_model_schema = model_map[base_model]

        base_model_schema_features = base_model_schema.features or []
        base_model_schema_model_properties = base_model_schema.model_properties or {}
        base_model_schema_parameters_rules = base_model_schema.parameter_rules or []

        entity = AIModelEntity(
            model=model,
            label=I18nObject(zh_hans=model, en_us=model),
            model_type=ModelType.LLM,
            features=list(base_model_schema_features),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties=dict(base_model_schema_model_properties.items()),
            parameter_rules=list(base_model_schema_parameters_rules),
            pricing=base_model_schema.pricing,
        )

        return entity
