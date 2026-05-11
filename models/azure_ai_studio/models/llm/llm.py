import json
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
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from dify_plugin.interfaces.model.large_language_model import LargeLanguageModel

logger = logging.getLogger(__name__)

# Forward these parameters to the Azure AI Inference SDK only when they
# are explicitly present in model_parameters. This avoids 400 errors from
# Azure-hosted models that reject temperature and top_p together.
_PASSTHROUGH_PARAMETERS = (
    "temperature",
    "top_p",
    "top_k",
    "max_tokens",
    "max_completion_tokens",
    "presence_penalty",
    "frequency_penalty",
    "seed",
    "reasoning_effort",
    "user",
)


class AzureAIStudioLargeLanguageModel(LargeLanguageModel):
    """
    Model class for Azure AI Studio large language model.
    """

    # Cache the client together with its signature so credential changes
    # do not accidentally reuse a client from another endpoint or API key.
    client: Any = None
    _client_signature: Optional[tuple] = None

    def _get_client(self, credentials: dict) -> ChatCompletionsClient:
        """
        Build or reuse the Azure AI Inference client.

        Recreate the client whenever endpoint, api_key, or api_version changes
        to prevent requests from leaking across credential sets.
        """
        endpoint = str(credentials.get("endpoint", ""))
        api_key = str(credentials.get("api_key", ""))
        api_version = credentials.get("api_version", "2024-05-01-preview")

        signature = (endpoint, api_key, api_version)
        if self.client is None or self._client_signature != signature:
            self.client = ChatCompletionsClient(
                endpoint=endpoint,
                credential=AzureKeyCredential(api_key),
                api_version=api_version,
            )
            self._client_signature = signature
        return self.client

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
        client = self._get_client(credentials)

        messages = [
            self._convert_prompt_message_to_dict(msg) for msg in prompt_messages
        ]

        # Forward only parameters explicitly configured by the user. Some
        # Azure-hosted Claude, o-series, and reasoning models reject requests
        # that include both temperature and top_p.
        payload: dict[str, Any] = {
            "messages": messages,
            "stream": stream,
            "model": model,
        }
        for key in _PASSTHROUGH_PARAMETERS:
            if key in model_parameters and model_parameters[key] is not None:
                payload[key] = model_parameters[key]

        # Handle response_format as either a string option or a prebuilt dict.
        response_format = model_parameters.get("response_format")
        if response_format:
            if isinstance(response_format, dict):
                payload["response_format"] = response_format
            elif response_format == "json_schema":
                json_schema_raw = model_parameters.get("json_schema")
                if not json_schema_raw:
                    raise ValueError(
                        "json_schema must be provided when response_format is json_schema"
                    )
                if isinstance(json_schema_raw, str):
                    try:
                        json_schema_raw = json.loads(json_schema_raw)
                    except json.JSONDecodeError as exc:
                        raise ValueError(
                            f"Invalid json_schema format: {exc}"
                        ) from exc
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": json_schema_raw,
                }
            elif response_format != "text":
                payload["response_format"] = {"type": response_format}

        # Merge user-configured and system-provided stop words, up to four.
        user_stop = model_parameters.get("stop")
        stop_words: list[str] = []
        if isinstance(user_stop, list):
            stop_words.extend([s for s in user_stop if isinstance(s, str) and s])
        elif isinstance(user_stop, str) and user_stop:
            stop_words.append(user_stop)
        if stop:
            stop_words.extend([s for s in stop if isinstance(s, str) and s])
        if stop_words:
            payload["stop"] = stop_words[:4]

        if tools:
            payload["tools"] = self._convert_tools(tools)

        try:
            response = client.complete(**payload)
            if stream:
                return self._handle_stream_response(response, model, prompt_messages)
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
            endpoint = str(credentials.get("endpoint", ""))
            api_key = str(credentials.get("api_key", ""))
            api_version = credentials.get("api_version", "2024-05-01-preview")
            if not endpoint or not api_key:
                raise CredentialsValidateFailedError(
                    "Both endpoint and api_key are required"
                )
            client = ChatCompletionsClient(
                endpoint=endpoint,
                credential=AzureKeyCredential(api_key),
                api_version=api_version,
            )
            # Do not send sampling parameters during validation, since some
            # Claude and o-series models reject restricted combinations.
            client.complete(
                messages=[
                    {"role": "user", "content": "I say 'ping', you say 'pong'.ping"},
                ],
                model=model,
            )
        except CredentialsValidateFailedError:
            raise
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
            InvokeRateLimitError: [],
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
                ValueError,
            ],
        }

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        """
        Used to define customizable model schema
        """
        # temperature and top_p are mutually exclusive or value-restricted on
        # some Azure-hosted Claude, mythos-preview, and o-series models. Keep
        # them optional so they are sent only when the user configures them.
        rules = [
            ParameterRule(
                name="temperature",
                type=ParameterType.FLOAT,
                use_template="temperature",
                required=False,
                label=I18nObject(zh_Hans="温度", en_US="Temperature"),
                help=I18nObject(
                    zh_Hans=(
                        "采样温度。部分模型（如 Claude opus-4-7、mythos-preview、"
                        "o-series 推理模型）不允许同时设置 temperature 和 top_p，"
                        "请只配置其中之一。"
                    ),
                    en_US=(
                        "Sampling temperature. Some models on Azure "
                        "(e.g. Claude opus-4-7, mythos-preview, o-series reasoning "
                        "models) do not allow temperature and top_p to be set at "
                        "the same time. Please configure only one of them."
                    ),
                ),
            ),
            ParameterRule(
                name="top_p",
                type=ParameterType.FLOAT,
                use_template="top_p",
                required=False,
                label=I18nObject(zh_Hans="Top P", en_US="Top P"),
                help=I18nObject(
                    zh_Hans=(
                        "核采样阈值。Claude opus-4-7 / mythos-preview 必须 ≥ 0.99，"
                        "且不要同时配置 temperature。"
                    ),
                    en_US=(
                        "Nucleus sampling threshold. For Claude opus-4-7 / "
                        "mythos-preview the value must be >= 0.99 and you should "
                        "not also set temperature."
                    ),
                ),
            ),
            ParameterRule(
                name="presence_penalty",
                type=ParameterType.FLOAT,
                use_template="presence_penalty",
                required=False,
                label=I18nObject(zh_Hans="存在惩罚", en_US="Presence Penalty"),
            ),
            ParameterRule(
                name="frequency_penalty",
                type=ParameterType.FLOAT,
                use_template="frequency_penalty",
                required=False,
                label=I18nObject(zh_Hans="频率惩罚", en_US="Frequency Penalty"),
            ),
            ParameterRule(
                name="max_tokens",
                type=ParameterType.INT,
                use_template="max_tokens",
                min=1,
                default=512,
                required=False,
                label=I18nObject(zh_Hans="最大生成长度", en_US="Max Tokens"),
                help=I18nObject(
                    zh_Hans=(
                        "生成内容的最大 token 数。OpenAI o-series / GPT-5 等推理"
                        "模型请改用 max_completion_tokens。"
                    ),
                    en_US=(
                        "Maximum number of tokens to generate. For OpenAI o-series "
                        "/ GPT-5 reasoning models please use max_completion_tokens "
                        "instead."
                    ),
                ),
            ),
            ParameterRule(
                name="max_completion_tokens",
                type=ParameterType.INT,
                required=False,
                min=1,
                label=I18nObject(
                    zh_Hans="最大补全长度", en_US="Max Completion Tokens"
                ),
                help=I18nObject(
                    zh_Hans=(
                        "用于 OpenAI o-series / GPT-5 等推理模型的输出长度限制。"
                        "若已设置 max_tokens 则忽略此项。"
                    ),
                    en_US=(
                        "Output length limit for OpenAI o-series / GPT-5 "
                        "reasoning models. Ignored when max_tokens is also set."
                    ),
                ),
            ),
            ParameterRule(
                name="seed",
                type=ParameterType.INT,
                required=False,
                label=I18nObject(zh_Hans="随机种子", en_US="Seed"),
                help=I18nObject(
                    zh_Hans="可复现采样的随机种子。",
                    en_US="Random seed used for reproducible sampling.",
                ),
            ),
            ParameterRule(
                name="response_format",
                type=ParameterType.STRING,
                required=False,
                options=["text", "json_object"],
                label=I18nObject(zh_Hans="响应格式", en_US="Response Format"),
                help=I18nObject(
                    zh_Hans=(
                        "强制模型按指定格式响应，json_object 要求模型输出合法 JSON。"
                    ),
                    en_US=(
                        "Force the model response to follow a specific format. "
                        "json_object requires the model to emit valid JSON."
                    ),
                ),
            ),
        ]

        # Expose reasoning_effort only when reasoning model support is enabled.
        if credentials.get("reasoning_support") == "true":
            rules.append(
                ParameterRule(
                    name="reasoning_effort",
                    type=ParameterType.STRING,
                    required=False,
                    options=["low", "medium", "high"],
                    label=I18nObject(zh_Hans="推理强度", en_US="Reasoning Effort"),
                    help=I18nObject(
                        zh_Hans="OpenAI o-series / GPT-5 推理模型的推理强度。",
                        en_US=(
                            "Reasoning effort level for OpenAI o-series / GPT-5 "
                            "reasoning models."
                        ),
                    ),
                )
            )

        features = []
        if credentials.get("vision_support") == "true":
            features.append(ModelFeature.VISION)
        if credentials.get("function_call_support") == "true":
            features.append(ModelFeature.TOOL_CALL)
            features.append(ModelFeature.MULTI_TOOL_CALL)
        if credentials.get("stream_tool_call_support") == "true":
            features.append(ModelFeature.STREAM_TOOL_CALL)

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
