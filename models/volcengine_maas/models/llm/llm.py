import json
import logging
from collections.abc import Generator
from typing import Optional

from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    I18nObject,
    ModelPropertyKey,
    ModelType,
    ParameterRule,
    ParameterType, ModelFeature,
)
from dify_plugin.entities.model.llm import (
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
)
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
from legacy.client import MaaSClient
from legacy.errors import (
    AuthErrors,
    BadRequestErrors,
    ConnectionErrors,
    MaasError,
    RateLimitErrors,
    ServerUnavailableErrors,
)
from models.client import ArkClientV3
from models.llm.models import (
    get_model_config,
    get_v2_req_params,
    get_v3_req_params,
)
from volcenginesdkarkruntime.types.chat import ChatCompletion, ChatCompletionChunk

logger = logging.getLogger(__name__)


class VolcengineMaaSLargeLanguageModel(LargeLanguageModel):
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
        if ArkClientV3.is_legacy(credentials):
            return self._generate_v2(
                model,
                credentials,
                prompt_messages,
                model_parameters,
                tools,
                stop,
                stream,
                user,
            )
        return self._generate_v3(
            model,
            credentials,
            prompt_messages,
            model_parameters,
            tools,
            stop,
            stream,
            user,
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate credentials
        """
        if ArkClientV3.is_legacy(credentials):
            return self._validate_credentials_v2(credentials)
        return self._validate_credentials_v3(credentials)

    @staticmethod
    def _validate_credentials_v2(credentials: dict) -> None:
        client = MaaSClient.from_credential(credentials)
        try:
            client.chat(
                {"max_new_tokens": 16, "temperature": 0.7, "top_p": 0.9, "top_k": 15},
                [UserPromptMessage(content="ping\nAnswer: ")],
            )
        except MaasError as e:
            raise CredentialsValidateFailedError(e.message)

    @staticmethod
    def _validate_credentials_v3(credentials: dict) -> None:
        client = ArkClientV3.from_credentials(credentials)
        try:
            client.chat(
                max_tokens=16,
                temperature=0.7,
                top_p=0.9,
                messages=[UserPromptMessage(content="ping\nAnswer: ")],
            )
        except Exception as e:
            raise CredentialsValidateFailedError(e)

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> int:
        if ArkClientV3.is_legacy(credentials):
            return self._get_num_tokens_v2(prompt_messages)
        return self._get_num_tokens_v3(prompt_messages)

    def _get_num_tokens_v2(self, messages: list[PromptMessage]) -> int:
        if len(messages) == 0:
            return 0
        num_tokens = 0
        messages_dict = [
            MaaSClient.convert_prompt_message_to_maas_message(m) for m in messages
        ]
        for message in messages_dict:
            for key, value in message.items():
                num_tokens += self._get_num_tokens_by_gpt2(str(key))
                num_tokens += self._get_num_tokens_by_gpt2(str(value))
        return num_tokens

    def _get_num_tokens_v3(self, messages: list[PromptMessage]) -> int:
        if len(messages) == 0:
            return 0
        num_tokens = 0
        messages_dict = [ArkClientV3.convert_prompt_message(m) for m in messages]
        for message in messages_dict:
            for key, value in message.items():
                # Ignore tokens for image type
                if isinstance(value, list):
                    text = ""
                    for item in value:
                        if isinstance(item, dict) and item["type"] == "text":
                            text += item["text"]

                    value = text
                num_tokens += self._get_num_tokens_by_gpt2(str(key))
                num_tokens += self._get_num_tokens_by_gpt2(str(value))
        return num_tokens

    def _generate_v2(
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
        client = MaaSClient.from_credential(credentials)
        req_params = get_v2_req_params(credentials, model_parameters, stop)
        extra_model_kwargs = {}
        if tools:
            extra_model_kwargs["tools"] = [
                MaaSClient.transform_tool_prompt_to_maas_config(tool) for tool in tools
            ]
        resp = MaaSClient.wrap_exception(
            lambda: client.chat(
                req_params, prompt_messages, stream, **extra_model_kwargs
            )
        )

        def _handle_stream_chat_response() -> Generator:
            for index, r in enumerate(resp):
                choices = r["choices"]
                if not choices:
                    continue
                choice = choices[0]
                message = choice["message"]
                usage = None
                if r.get("usage"):
                    usage = self._calc_response_usage(
                        model=model,
                        credentials=credentials,
                        prompt_tokens=r["usage"]["prompt_tokens"],
                        completion_tokens=r["usage"]["completion_tokens"],
                    )
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=index,
                        message=AssistantPromptMessage(
                            content=message["content"] or "", tool_calls=[]
                        ),
                        usage=usage,
                        finish_reason=choice.get("finish_reason"),
                    ),
                )

        def _handle_chat_response() -> LLMResult:
            choices = resp["choices"]
            if not choices:
                raise ValueError("No choices found")
            choice = choices[0]
            message = choice["message"]
            tool_calls = []
            if message["tool_calls"]:
                for call in message["tool_calls"]:
                    tool_call = AssistantPromptMessage.ToolCall(
                        id=call["function"]["name"],
                        type=call["type"],
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=call["function"]["name"],
                            arguments=call["function"]["arguments"],
                        ),
                    )
                    tool_calls.append(tool_call)
            usage = resp["usage"]
            return LLMResult(
                model=model,
                prompt_messages=prompt_messages,
                message=AssistantPromptMessage(
                    content=message["content"] or "", tool_calls=tool_calls
                ),
                usage=self._calc_response_usage(
                    model=model,
                    credentials=credentials,
                    prompt_tokens=usage["prompt_tokens"],
                    completion_tokens=usage["completion_tokens"],
                ),
            )

        if not stream:
            return _handle_chat_response()
        return _handle_stream_chat_response()

    def wrap_thinking(self, delta: dict, is_reasoning: bool) -> tuple[str, bool]:
        content = ""
        reasoning_content = None
        if hasattr(delta, "content"):
            content = delta.content
        if hasattr(delta, "reasoning_content"):
            reasoning_content = delta.reasoning_content
        return self._wrap_thinking_by_reasoning_content(
            {"content": content, "reasoning_content": reasoning_content}, is_reasoning
        )

    def _generate_v3(
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
        client = ArkClientV3.from_credentials(credentials)

        # Process structured output parameters
        if "response_format" in model_parameters:
            response_format = model_parameters.get("response_format")
            if response_format == "json_schema":
                json_schema = model_parameters.get("json_schema")
                if not json_schema:
                    raise ValueError(
                        "Must define JSON Schema when the response format is json_schema"
                    )
                try:
                    schema = json.loads(json_schema)
                except Exception:
                    raise ValueError(f"not correct json_schema format: {json_schema}")
                model_parameters.pop("json_schema")
                model_parameters["response_format"] = {
                    "type": "json_schema",
                    "json_schema": schema,
                }
            else:
                model_parameters["response_format"] = {"type": response_format}
        elif "json_schema" in model_parameters:
            del model_parameters["json_schema"]

        req_params = get_v3_req_params(credentials, model_parameters, stop)
        if tools:
            req_params["tools"] = tools

        def _handle_stream_chat_response(chunks: Generator[ChatCompletionChunk]) -> Generator:
            is_reasoning_started = False
            chunk_index = 0
            full_assistant_content = ""
            finish_reason = None
            usage = None
            tools_calls: list[AssistantPromptMessage.ToolCall] = []
            for chunk in chunks:
                chunk_index += 1
                if chunk:
                    delta_content = ""
                    if chunk.usage:
                        usage = self._calc_response_usage(
                            model=model,
                            credentials=credentials,
                            prompt_tokens=chunk.usage.prompt_tokens,
                            completion_tokens=chunk.usage.completion_tokens,
                        )
                    if chunk.choices:
                        finish_reason = chunk.choices[0].finish_reason
                        delta = chunk.choices[0].delta
                        delta_content, is_reasoning_started = self.wrap_thinking(delta, is_reasoning_started)

                        if delta.tool_calls:
                            tools_calls = self._increase_tool_call(delta.tool_calls, tools_calls)

                    assistant_prompt_message = AssistantPromptMessage(
                        content=delta_content,
                    )
                    full_assistant_content += delta_content
                    yield LLMResultChunk(
                        model=model,
                        prompt_messages=prompt_messages,
                        delta=LLMResultChunkDelta(
                            index=chunk_index,
                            message=assistant_prompt_message,
                        ),
                    )

            if tools_calls:
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=chunk_index,
                        message=AssistantPromptMessage(tool_calls=tools_calls, content=""),
                    ),
                )

            yield self._create_final_llm_result_chunk(
                index=chunk_index,
                message=AssistantPromptMessage(content=""),
                finish_reason=finish_reason,
                usage=usage,
                model=model,
                credentials=credentials,
                prompt_messages=prompt_messages,
                full_content=full_assistant_content,
            )

        def _handle_chat_response(resp: ChatCompletion) -> LLMResult:
            choice = resp.choices[0]
            message = choice.message
            # parse tool calls
            tool_calls = []
            if message.tool_calls:
                for call in message.tool_calls:
                    tool_call = AssistantPromptMessage.ToolCall(
                        id=call.id,
                        type=call.type,
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=call.function.name, arguments=call.function.arguments
                        ),
                    )
                    tool_calls.append(tool_call)

            usage = resp.usage
            return LLMResult(
                model=model,
                prompt_messages=prompt_messages,
                message=AssistantPromptMessage(
                    content=message.content or "",
                    tool_calls=tool_calls,
                ),
                usage=self._calc_response_usage(
                    model=model,
                    credentials=credentials,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                ),
            )

        if not stream:
            resp = client.chat(prompt_messages, **req_params)
            return _handle_chat_response(resp)

        chunks = client.stream_chat(prompt_messages, **req_params)
        return _handle_stream_chat_response(chunks)

    def _create_final_llm_result_chunk(
        self,
        index: int,
        message: AssistantPromptMessage,
        finish_reason: str,
        usage: dict,
        model: str,
        prompt_messages: list[PromptMessage],
        credentials: dict,
        full_content: str,
    ) -> LLMResultChunk:
        # calculate num tokens
        prompt_tokens = usage and usage.prompt_tokens
        if prompt_tokens is None:
            prompt_tokens = self._num_tokens_from_string(text=prompt_messages[0].content)
        completion_tokens = usage and usage.completion_tokens
        if completion_tokens is None:
            completion_tokens = self._num_tokens_from_string(text=full_content)

        # transform usage
        usage = self._calc_response_usage(model, credentials, prompt_tokens, completion_tokens)

        return LLMResultChunk(
            model=model,
            prompt_messages=prompt_messages,
            delta=LLMResultChunkDelta(index=index, message=message, finish_reason=finish_reason, usage=usage),
        )

    def _extract_response_tool_calls(self, response_tool_calls: list[dict]) -> list[AssistantPromptMessage.ToolCall]:
        """
        Extract tool calls from response

        :param response_tool_calls: response tool calls
        :return: list of tool calls
        """
        tool_calls = []
        if response_tool_calls:
            for response_tool_call in response_tool_calls:
                function = AssistantPromptMessage.ToolCall.ToolCallFunction(
                    name=response_tool_call.get("function", {}).get("name", ""),
                    arguments=response_tool_call.get("function", {}).get("arguments", ""),
                )

                tool_call = AssistantPromptMessage.ToolCall(
                    id=response_tool_call.get("id", ""), type=response_tool_call.get("type", ""), function=function
                )
                tool_calls.append(tool_call)

        return tool_calls

    def _increase_tool_call(
        self, new_tool_calls: list[AssistantPromptMessage.ToolCall], tools_calls: list[AssistantPromptMessage.ToolCall]
    ) -> list[AssistantPromptMessage.ToolCall]:
        for new_tool_call in new_tool_calls:
            # get tool call
            tool_call, tools_calls = self._get_tool_call(new_tool_call.function.name, tools_calls)
            # update tool call
            if new_tool_call.id:
                tool_call.id = new_tool_call.id
            if new_tool_call.type:
                tool_call.type = new_tool_call.type
            if new_tool_call.function.name:
                tool_call.function.name = new_tool_call.function.name
            if new_tool_call.function.arguments:
                tool_call.function.arguments += new_tool_call.function.arguments
        return tools_calls

    def _get_tool_call(self, tool_call_id: str, tools_calls: list[AssistantPromptMessage.ToolCall]):
        """
        Get or create a tool call by ID

        :param tool_call_id: tool call ID
        :param tools_calls: list of existing tool calls
        :return: existing or new tool call, updated tools_calls
        """
        if not tool_call_id:
            return tools_calls[-1], tools_calls

        tool_call = next((tool_call for tool_call in tools_calls if tool_call.id == tool_call_id), None)
        if tool_call is None:
            tool_call = AssistantPromptMessage.ToolCall(
                id=tool_call_id,
                type="function",
                function=AssistantPromptMessage.ToolCall.ToolCallFunction(name="", arguments=""),
            )
            tools_calls.append(tool_call)

        return tool_call, tools_calls

    def get_customizable_model_schema(self, model: str, credentials: dict) -> Optional[AIModelEntity]:
        """
        used to define customizable model schema
        """
        model_config = get_model_config(credentials)
        if model.lower().startswith("deepseek-r1"):
            rules = [
                ParameterRule(
                    name="max_tokens",
                    type=ParameterType.INT,
                    use_template="max_tokens",
                    min=1,
                    max=model_config.properties.max_tokens,
                    default=512,
                    label=I18nObject(zh_Hans="最大生成长度", en_US="Max Tokens"),
                ),
                ParameterRule(
                    name="skip_moderation",
                    type=ParameterType.BOOLEAN,
                    default=False,
                    label=I18nObject(zh_Hans="跳过内容审核", en_US="Skip Moderation"),
                    help=I18nObject(zh_Hans="跳过内容审核，需要先联系火山引擎开通此功能",
                                    en_US="Skip Moderation, please contact Volcengine to enable this feature first"),
                ),
            ]
        else:
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
                    name="top_k",
                    type=ParameterType.INT,
                    min=1,
                    default=1,
                    label=I18nObject(zh_Hans="Top K", en_US="Top K"),
                ),
                ParameterRule(
                    name="presence_penalty",
                    type=ParameterType.FLOAT,
                    use_template="presence_penalty",
                    label=I18nObject(en_US="Presence Penalty", zh_Hans="存在惩罚"),
                    min=-2.0,
                    max=2.0,
                ),
                ParameterRule(
                    name="frequency_penalty",
                    type=ParameterType.FLOAT,
                    use_template="frequency_penalty",
                    label=I18nObject(en_US="Frequency Penalty", zh_Hans="频率惩罚"),
                    min=-2.0,
                    max=2.0,
                ),
                ParameterRule(
                    name="max_tokens",
                    type=ParameterType.INT,
                    use_template="max_tokens",
                    min=1,
                    max=model_config.properties.max_tokens,
                    default=512,
                    label=I18nObject(zh_Hans="最大生成长度", en_US="Max Tokens"),
                ),
                ParameterRule(
                    name="skip_moderation",
                    type=ParameterType.BOOLEAN,
                    default=False,
                    label=I18nObject(zh_Hans="跳过内容审核", en_US="Skip Moderation"),
                    help=I18nObject(zh_Hans="跳过内容审核，需要先联系火山引擎开通此功能",
                                    en_US="Skip Moderation, please contact Volcengine to enable this feature first"),
                ),
            ]
        base_model = credentials.get("base_model_name", "")
        if base_model.lower() in ("doubao-1.5-thinking-pro", "doubao-seed-1.6"):
            rules.append(
                ParameterRule(
                    name="thinking",
                    type=ParameterType.STRING,
                    default="enabled",
                    label=I18nObject(zh_Hans="深度思考模式", en_US="thinking"),
                    options=["enabled", "disabled", "auto"],
                )
            )
        elif base_model.lower() in ("doubao-1.5-thinking-vision-pro", "doubao-seed-1.6-flash", "deepseek-v3.1",
                                    "doubao-seed-1.6-vision"):
            rules.append(
                ParameterRule(
                    name="thinking",
                    type=ParameterType.STRING,
                    default="enabled",
                    label=I18nObject(zh_Hans="深度思考模式", en_US="thinking"),
                    options=["enabled", "disabled"],
                )
            )

        # Add structured output parameters for supported models
        if ModelFeature.STRUCTURED_OUTPUT in model_config.features:
            rules.extend([
                ParameterRule(
                    name="response_format",
                    type=ParameterType.STRING,
                    default="text",
                    label=I18nObject(zh_Hans="响应格式", en_US="Response Format"),
                    help=I18nObject(zh_Hans="指定模型响应的格式", en_US="Specify the format of model response"),
                    options=["text", "json_object", "json_schema"],
                ),
                ParameterRule(
                    name="json_schema",
                    type=ParameterType.STRING,
                    label=I18nObject(zh_Hans="JSON Schema", en_US="JSON Schema"),
                    help=I18nObject(zh_Hans="当response_format为json_schema时必需，定义JSON响应的结构",
                                    en_US="Required when response_format is json_schema, defines the structure of JSON response"),
                ),
            ])

        model_properties = {}
        model_properties[ModelPropertyKey.CONTEXT_SIZE] = (
            model_config.properties.context_size
        )
        model_properties[ModelPropertyKey.MODE] = model_config.properties.mode.value
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_US=model),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.LLM,
            model_properties=model_properties,
            parameter_rules=rules,
            features=model_config.features,
            pricing=model_config.pricing,
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
            InvokeConnectionError: ConnectionErrors.values(),
            InvokeServerUnavailableError: ServerUnavailableErrors.values(),
            InvokeRateLimitError: RateLimitErrors.values(),
            InvokeAuthorizationError: AuthErrors.values(),
            InvokeBadRequestError: BadRequestErrors.values(),
        }
