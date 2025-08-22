import base64
import os
import tempfile
import uuid
from collections.abc import Generator
from http import HTTPStatus
from pathlib import Path
from typing import Optional, Union, cast

import requests
from dashscope import Generation, MultiModalConversation, get_tokenizer
from dashscope.api_entities.dashscope_response import GenerationResponse
from dashscope.common.error import (
    AuthenticationError,
    InvalidParameter,
    RequestFailure,
    ServiceUnavailableError,
    UnsupportedHTTPMethod,
    UnsupportedModel,
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
    DocumentPromptMessageContent,
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageRole,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
    VideoPromptMessageContent,
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
from openai import OpenAI


class TongyiLargeLanguageModel(LargeLanguageModel):
    tokenizers = {}

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
        return self._generate(
            model,
            credentials,
            prompt_messages,
            model_parameters,
            tools,
            stop,
            stream,
            user,
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
        if self.get_customizable_model_schema(model, credentials) is not None:
            return 0
        if model in {"qwen-turbo-chat", "qwen-plus-chat"}:
            model = model.replace("-chat", "")
        if model == "farui-plus":
            model = "qwen-farui-plus"
        if model in self.tokenizers:
            tokenizer = self.tokenizers[model]
        else:
            tokenizer = get_tokenizer(model)
            self.tokenizers[model] = tokenizer
        tokens = tokenizer.encode(self._convert_messages_to_prompt(prompt_messages))
        return len(tokens)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            self._generate(
                model=model,
                credentials=credentials,
                prompt_messages=[UserPromptMessage(content="ping")],
                model_parameters={"temperature": 0.5},
                stream=False,
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _generate(
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
        :param credentials: credentials
        :param prompt_messages: prompt messages
        :param tools: tools for tool calling
        :param model_parameters: model parameters
        :param stop: stop words
        :param stream: is stream response
        :param user: unique user id
        :return: full response or stream response chunk generator result
        """
        if credentials.get("use_international_endpoint", "false") == "true":
            import dashscope
            dashscope.base_http_api_url = "https://dashscope-intl.aliyuncs.com/api/v1"
        credentials_kwargs = self._to_credential_kwargs(credentials)
        mode = self.get_model_mode(model, credentials)
        if model in {"qwen-turbo-chat", "qwen-plus-chat"}:
            model = model.replace("-chat", "")
        extra_model_kwargs = {}
        if tools:
            extra_model_kwargs["tools"] = self._convert_tools(tools)
        if stop:
            extra_model_kwargs["stop"] = stop

        response_format = model_parameters.get("response_format")
        if response_format:
            model_parameters["response_format"] = {"type": response_format}

        if model.startswith("qwen-mt"):
            source_lang = model_parameters.pop("source_lang", None)
            target_lang = model_parameters.pop("target_lang", None)
            domains = model_parameters.pop("domains", None)
            model_parameters["translation_options"] = {
                "source_lang": source_lang,
                "target_lang": target_lang,
                "domains": domains,
            }
            # The Qwen-MT model does not support incremental streaming output at this time.
            stream = False
            if len(prompt_messages) > 1:
                prompt_messages = prompt_messages[-1:]
            if prompt_messages[-1].role != PromptMessageRole.USER:
                raise ValueError("There is one and only one User Message in the messages array.")

        params = {
            "model": model,
            **model_parameters,
            **credentials_kwargs,
            **extra_model_kwargs,
        }
        model_schema = self.get_model_schema(model, credentials)

        incremental_output = False if tools else stream

        thinking_business_qwen3 = model in ("qwen-plus-latest", "qwen-plus-2025-04-28",
                                            "qwen-turbo-latest", "qwen-turbo-2025-04-28") \
                                  and model_parameters.get("enable_thinking", False)

        # Qwen3 business edition (Thinking Mode), Qwen3 open-source edition, QwQ, and QVQ models only supports streaming output.
        if thinking_business_qwen3 or model.startswith(("qwen3-", "qwq-", "qvq-")):
            stream = True

        # Qwen3 business edition (Thinking Mode), Qwen3 open-source edition and QwQ models only supports incremental_output set to True.
        if thinking_business_qwen3 or model.startswith(("qwen3-", "qwq-", "qvq-")):
            incremental_output = True

        if ModelFeature.VISION in (model_schema.features or []):
            params["messages"] = self._convert_prompt_messages_to_tongyi_messages(
                credentials, prompt_messages, rich_content=True
            )
            response = MultiModalConversation.call(**params, stream=stream, incremental_output=incremental_output)
        else:
            params["messages"] = self._convert_prompt_messages_to_tongyi_messages(
                credentials, prompt_messages
            )
            response = Generation.call(
                **params,
                result_format="message",
                stream=stream,
                incremental_output=incremental_output,
            )
        if stream:
            return self._handle_generate_stream_response(
                model, credentials, response, prompt_messages, incremental_output,
            )
        return self._handle_generate_response(
            model, credentials, response, prompt_messages
        )

    def _handle_generate_response(
        self,
        model: str,
        credentials: dict,
        response: GenerationResponse,
        prompt_messages: list[PromptMessage],
    ) -> LLMResult:
        """
        Handle llm response

        :param model: model name
        :param credentials: credentials
        :param response: response
        :param prompt_messages: prompt messages
        :return: llm response
        """
        if response.status_code not in {200, HTTPStatus.OK}:
            raise ServiceUnavailableError(response.message)
        resp_content = response.output.choices[0].message.content
        # special for qwen-vl
        if isinstance(resp_content, list):
            resp_content = resp_content[0]["text"]
        assistant_prompt_message = AssistantPromptMessage(content=resp_content)
        usage = self._calc_response_usage(
            model,
            credentials,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        result = LLMResult(
            model=model,
            message=assistant_prompt_message,
            prompt_messages=prompt_messages,
            usage=usage,
        )
        return result

    def _handle_tool_call_stream(self, response, tool_calls, incremental_output):
        tool_calls_stream = response.output.choices[0].message["tool_calls"]
        for tool_call_stream in tool_calls_stream:
            idx = tool_call_stream.get('index')
            if idx >= len(tool_calls):
                tool_calls.append(tool_call_stream)
            else:
                if tool_call_stream.get('function'):
                    func_name = tool_call_stream.get('function').get('name')
                    tool_call_obj = tool_calls[idx]
                    if func_name:
                        if incremental_output:
                            tool_call_obj['function']['name'] += func_name
                        else:
                            tool_call_obj['function']['name'] = func_name
                    args = tool_call_stream.get('function').get('arguments')
                    if args:
                        if incremental_output:
                            tool_call_obj['function']['arguments'] += args
                        else:
                            tool_call_obj['function']['arguments'] = args

    def _handle_generate_stream_response(
        self,
        model: str,
        credentials: dict,
        responses: Generator[GenerationResponse, None, None],
        prompt_messages: list[PromptMessage],
        incremental_output: bool,
    ) -> Generator:
        """
        Handle llm stream response

        :param model: model name
        :param credentials: credentials
        :param responses: response
        :param prompt_messages: prompt messages
        :param incremental_output: is incremental output
        :return: llm response chunk generator result
        """
        is_reasoning = False
        # This is used to handle unincremental output correctly
        full_text = ""
        tool_calls = []
        for index, response in enumerate(responses):
            if response.status_code not in {200, HTTPStatus.OK}:
                raise ServiceUnavailableError(
                    f"Failed to invoke model {model}, status code: {response.status_code}, message: {response.message}"
                )
            resp_finish_reason = response.output.choices[0].finish_reason
            if resp_finish_reason is not None and resp_finish_reason != "null":
                resp_content = response.output.choices[0].message.content
                assistant_prompt_message = AssistantPromptMessage(content="")
                if "tool_calls" in response.output.choices[0].message:
                    self._handle_tool_call_stream(response, tool_calls, incremental_output)
                elif resp_content:
                    if isinstance(resp_content, list):
                        resp_content = resp_content[0]["text"]
                    if incremental_output:
                        assistant_prompt_message.content = resp_content
                        full_text += resp_content
                    else:
                        assistant_prompt_message.content = resp_content.replace(
                            full_text, "", 1
                        )
                        full_text = resp_content
                if tool_calls:
                    message_tool_calls = []
                    for tool_call_obj in tool_calls:
                        message_tool_call = AssistantPromptMessage.ToolCall(
                            id=tool_call_obj["function"]["name"],
                            type="function",
                            function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                name=tool_call_obj["function"]["name"],
                                arguments=tool_call_obj["function"]["arguments"],
                            ),
                        )
                        message_tool_calls.append(message_tool_call)
                    assistant_prompt_message.tool_calls = message_tool_calls
                usage = response.usage
                usage = self._calc_response_usage(
                    model, credentials, usage.input_tokens, usage.output_tokens
                )
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=index,
                        message=assistant_prompt_message,
                        finish_reason=resp_finish_reason,
                        usage=usage,
                    ),
                )
            else:
                message = response.output.choices[0].message

                resp_content, is_reasoning = self._wrap_thinking_by_reasoning_content(
                    message, is_reasoning
                )
                if not resp_content:
                    if "tool_calls" in response.output.choices[0].message:
                        self._handle_tool_call_stream(response, tool_calls, incremental_output)
                    continue
                if isinstance(resp_content, list):
                    resp_content = resp_content[0]["text"]
                if incremental_output:
                    delta = resp_content
                    full_text += delta
                else:
                    delta = resp_content.replace(full_text, "", 1)
                    full_text = resp_content

                assistant_prompt_message = AssistantPromptMessage(
                    content=delta
                )
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=index, message=assistant_prompt_message
                    ),
                )

    def _to_credential_kwargs(self, credentials: dict) -> dict:
        """
        Transform credentials to kwargs for model instance

        :param credentials:
        :return:
        """
        credentials_kwargs = {"api_key": credentials["dashscope_api_key"]}
        return credentials_kwargs

    def _convert_one_message_to_text(self, message: PromptMessage) -> str:
        """
        Convert a single message to a string.

        :param message: PromptMessage to convert.
        :return: String representation of the message.
        """
        human_prompt = "\n\nHuman:"
        ai_prompt = "\n\nAssistant:"
        content = message.content
        if isinstance(message, UserPromptMessage):
            if isinstance(content, str):
                message_text = f"{human_prompt} {content}"
            elif isinstance(content, list):
                message_text = ""
                for sub_message in content:
                    if sub_message.type == PromptMessageContentType.TEXT:
                        message_text = f"{human_prompt} {sub_message.data}"
                        break
            else:
                raise TypeError(f"[convert_one_message_to_text] Unexpected content type: {type(content)}")
        elif isinstance(message, AssistantPromptMessage):
            message_text = f"{ai_prompt} {content}"
        elif isinstance(message, SystemPromptMessage | ToolPromptMessage):
            message_text = content
        else:
            raise ValueError(f"Got unknown type {message}")
        return message_text

    def _convert_messages_to_prompt(self, messages: list[PromptMessage]) -> str:
        """
        Format a list of messages into a full prompt for the Anthropic model

        :param messages: List of PromptMessage to combine.
        :return: Combined string with necessary human_prompt and ai_prompt tags.
        """
        messages = messages.copy()
        text = "".join(
            (self._convert_one_message_to_text(message) for message in messages)
        )
        return text.rstrip()

    def _convert_prompt_messages_to_tongyi_messages(
        self,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        rich_content: bool = False,
    ) -> list[dict]:
        """
        Convert prompt messages to tongyi messages

        :param prompt_messages: prompt messages
        :return: tongyi messages
        """
        tongyi_messages = []
        for prompt_message in prompt_messages:
            if isinstance(prompt_message, SystemPromptMessage):
                tongyi_messages.append(
                    {
                        "role": "system",
                        "content": (
                            prompt_message.content
                            if not rich_content
                            else [{"text": prompt_message.content}]
                        ),
                    }
                )
            elif isinstance(prompt_message, UserPromptMessage):
                if isinstance(prompt_message.content, str):
                    tongyi_messages.append(
                        {
                            "role": "user",
                            "content": (
                                prompt_message.content
                                if not rich_content
                                else [{"text": prompt_message.content}]
                            ),
                        }
                    )
                else:
                    user_messages = []
                    file_id_list = []
                    for message_content in prompt_message.content:
                        if message_content.type == PromptMessageContentType.TEXT:
                            message_content = cast(
                                TextPromptMessageContent, message_content
                            )
                            sub_message_dict = {"text": message_content.data}
                            user_messages.append(sub_message_dict)
                        elif message_content.type == PromptMessageContentType.IMAGE:
                            message_content = cast(
                                ImagePromptMessageContent, message_content
                            )
                            image_url = message_content.data
                            if message_content.data.startswith("data:"):
                                image_url = self._save_base64_to_file(message_content.data)
                            sub_message_dict = {"image": image_url}
                            user_messages.append(sub_message_dict)
                        elif message_content.type == PromptMessageContentType.VIDEO:
                            message_content = cast(
                                VideoPromptMessageContent, message_content
                            )
                            video_url = message_content.data
                            if message_content.data.startswith("data:"):
                                video_url = self._save_base64_to_file(message_content.data)
                            sub_message_dict = {"video": video_url}
                            user_messages.append(sub_message_dict)
                        elif message_content.type == PromptMessageContentType.DOCUMENT:
                            message_content = cast(
                                DocumentPromptMessageContent, message_content
                            )
                            file_id = self._upload_file_to_tongyi(
                                credentials, message_content
                            )
                            file_id_url = f"fileid://{file_id}"
                            file_id_list.append(file_id_url)
                    if len(file_id_list) > 0:
                        tongyi_messages.append(
                            {"role": "system", "content": ",".join(file_id_list)}
                        )
                    user_messages = sorted(user_messages, key=lambda x: "text" in x)
                    tongyi_messages.append({"role": "user", "content": user_messages})
            elif isinstance(prompt_message, AssistantPromptMessage):
                content = prompt_message.content
                if not content:
                    content = " "
                message = {
                    "role": "assistant",
                    "content": content if not rich_content else [{"text": content}],
                }
                if prompt_message.tool_calls:
                    message["tool_calls"] = [
                        tool_call.model_dump()
                        for tool_call in prompt_message.tool_calls
                    ]
                tongyi_messages.append(message)
            elif isinstance(prompt_message, ToolPromptMessage):
                tongyi_messages.append(
                    {
                        "role": "tool",
                        "content": prompt_message.content,
                        "name": prompt_message.tool_call_id,
                    }
                )
            else:
                raise ValueError(f"Got unknown type {prompt_message}")
        return tongyi_messages

    def _save_base64_to_file(self, base64_data: str) -> str:
        """
        Save base64 data to file
        'data:{upload_file.mime_type};base64,{encoded_string}'
        
        :param base64_data: base64 data
        :return: file path
        """
        (mime_type, encoded_string) = (
            base64_data.split(",")[0].split(";")[0].split(":")[1],
            base64_data.split(",")[1],
        )
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, f"{uuid.uuid4()}.{mime_type.split('/')[1]}")
        Path(file_path).write_bytes(base64.b64decode(encoded_string))
        return f"file://{file_path}"

    def _upload_file_to_tongyi(
        self, credentials: dict, message_content: DocumentPromptMessageContent
    ) -> str:
        """
        Upload file to Tongyi

        :param credentials: credentials for Tongyi
        :param message_content: message content to upload
        :return: file ID in Tongyi
        """
        client = OpenAI(
            api_key=credentials.dashscope_api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        if credentials.get("use_international_endpoint", "false") == "true":
            client = OpenAI(
                api_key=credentials.dashscope_api_key,
                base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            )
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            if message_content.base64_data:
                file_content = base64.b64decode(message_content.base64_data)
                temp_file.write(file_content)
            else:
                try:
                    response = requests.get(message_content.url, timeout=60)
                    response.raise_for_status()
                    temp_file.write(response.content)
                except Exception as ex:
                    raise ValueError(
                        f"Failed to fetch data from url {message_content.url}, {ex}"
                    ) from ex
            temp_file.flush()
        response = client.files.create(file=temp_file, purpose="file-extract")
        return response.id

    def _convert_tools(self, tools: list[PromptMessageTool]) -> list[dict]:
        """
        Convert tools
        """
        tool_definitions = []
        for tool in tools:
            properties = tool.parameters["properties"]
            required_properties = tool.parameters["required"]
            properties_definitions = {}
            for p_key, p_val in properties.items():
                desc = p_val["description"]
                if "enum" in p_val:
                    desc += f"; Only accepts one of the following predefined options: [{', '.join(p_val['enum'])}]"
                properties_definitions[p_key] = {
                    "description": desc,
                    "type": p_val["type"],
                }
            tool_definition = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": properties_definitions,
                    "required": required_properties,
                },
            }
            tool_definitions.append(tool_definition)
        return tool_definitions

    def _wrap_thinking_by_reasoning_content(self, delta: dict, is_reasoning: bool) -> tuple[str, bool]:
        """
        If the reasoning response is from delta.get("reasoning_content"), we wrap
        it with HTML think tag.
        :param delta: delta dictionary from LLM streaming response
        :param is_reasoning: is reasoning
        :return: tuple of (processed_content, is_reasoning)
        """

        content = delta.get("content") or ""
        reasoning_content = delta.get("reasoning_content")
        try:
            if reasoning_content:
                try:
                    if isinstance(reasoning_content, list):
                        reasoning_content = "\n".join(map(str, reasoning_content))
                    elif not isinstance(reasoning_content, str):
                        reasoning_content = str(reasoning_content)

                    if not is_reasoning:
                        content = "<think>\n" + reasoning_content
                        is_reasoning = True
                    else:
                        content = reasoning_content
                except Exception as ex:
                    raise ValueError(
                        f"[wrap_thinking_by_reasoning_content-1] {ex}"
                    ) from ex
            elif is_reasoning and content:
                if not isinstance(content, list):
                    content = str(content)
                else:
                    content = ""
                content = "\n</think>" + content
                is_reasoning = False
        except Exception as ex:
            raise ValueError(
                f"[wrap_thinking_by_reasoning_content-2] {ex}"
            ) from ex
        return content, is_reasoning

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
            InvokeConnectionError: [RequestFailure],
            InvokeServerUnavailableError: [ServiceUnavailableError],
            InvokeRateLimitError: [],
            InvokeAuthorizationError: [AuthenticationError],
            InvokeBadRequestError: [
                InvalidParameter,
                UnsupportedModel,
                UnsupportedHTTPMethod,
            ],
        }

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        """
        Architecture for defining customizable models

        :param model: model name
        :param credentials: model credentials
        :return: AIModelEntity or None
        """
        return AIModelEntity(
            model=model,
            label=I18nObject(en_US=model, zh_Hans=model),
            model_type=ModelType.LLM,
            features=(
                [
                    ModelFeature.TOOL_CALL,
                    ModelFeature.MULTI_TOOL_CALL,
                    ModelFeature.STREAM_TOOL_CALL,
                ]
                if credentials.get("function_calling_type") == "tool_call"
                else []
            ),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(
                    credentials.get("context_size", 8000)
                ),
                ModelPropertyKey.MODE: LLMMode.CHAT.value,
            },
            parameter_rules=[
                ParameterRule(
                    name="temperature",
                    use_template="temperature",
                    label=I18nObject(en_US="Temperature", zh_Hans="温度"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="max_tokens",
                    use_template="max_tokens",
                    default=512,
                    min=1,
                    max=int(credentials.get("max_tokens", 1024)),
                    label=I18nObject(en_US="Max Tokens", zh_Hans="最大标记"),
                    type=ParameterType.INT,
                ),
                ParameterRule(
                    name="top_p",
                    use_template="top_p",
                    label=I18nObject(en_US="Top P", zh_Hans="Top P"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="top_k",
                    use_template="top_k",
                    label=I18nObject(en_US="Top K", zh_Hans="Top K"),
                    type=ParameterType.FLOAT,
                ),
                ParameterRule(
                    name="frequency_penalty",
                    use_template="frequency_penalty",
                    label=I18nObject(en_US="Frequency Penalty", zh_Hans="重复惩罚"),
                    type=ParameterType.FLOAT,
                ),
            ],
        )
