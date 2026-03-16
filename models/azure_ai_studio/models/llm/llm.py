import json
import logging
import re
from collections.abc import Generator, Sequence
from typing import Any, Optional, Union
from urllib import error as urllib_error
from urllib import request as urllib_request

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
    InvokeServerUnavailableError,
)
from dify_plugin.interfaces.model.large_language_model import LargeLanguageModel

logger = logging.getLogger(__name__)


class AzureAIStudioLargeLanguageModel(LargeLanguageModel):
    """
    Model class for Azure AI Studio large language model.
    """

    client: Any = None
    from azure.ai.inference.models import StreamingChatCompletionsUpdate

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

    # =========================================================================
    # Azure Anthropic Foundry Support
    # =========================================================================

    def _is_anthropic_foundry_endpoint(self, endpoint: str) -> bool:
        """Check if the endpoint is an Azure Anthropic Foundry endpoint."""
        endpoint = (endpoint or "").lower()
        return ".services.ai.azure.com/anthropic" in endpoint or endpoint.endswith("/anthropic")

    def _normalize_anthropic_endpoint(self, endpoint: str) -> str:
        """Normalize endpoint by removing trailing path components."""
        endpoint = (endpoint or "").rstrip("/")
        for suffix in ("/v1/messages", "/v1", "/messages"):
            if endpoint.endswith(suffix):
                endpoint = endpoint[: -len(suffix)]
                break
        return endpoint

    def _anthropic_messages_url(self, endpoint: str) -> str:
        """Build the Anthropic Messages API URL."""
        return f"{self._normalize_anthropic_endpoint(endpoint)}/v1/messages"

    def _parse_data_uri(self, value: str) -> tuple[str, str] | None:
        """Parse a data URI into media type and base64 data."""
        match = re.match(r"^data:(?P<media_type>[^;]+);base64,(?P<data>.+)$", value or "", re.DOTALL)
        if not match:
            return None
        return (match.group("media_type"), match.group("data"))

    def _convert_prompt_messages_to_anthropic(
        self, prompt_messages: Sequence[PromptMessage]
    ) -> tuple[str | None, list[dict]]:
        """Convert Dify prompt messages to Anthropic Messages API format."""
        system_parts: list[str] = []
        messages: list[dict] = []

        for message in prompt_messages:
            if isinstance(message, SystemPromptMessage):
                if isinstance(message.content, str):
                    system_parts.append(message.content)
                elif isinstance(message.content, list):
                    for content in message.content:
                        if getattr(content, "type", None) == PromptMessageContentType.TEXT:
                            system_parts.append(content.data)
                continue

            if isinstance(message, UserPromptMessage):
                if isinstance(message.content, str):
                    messages.append({"role": "user", "content": message.content})
                elif isinstance(message.content, list):
                    content_blocks: list[dict] = []
                    for content in message.content:
                        if content.type == PromptMessageContentType.TEXT:
                            content_blocks.append({"type": "text", "text": content.data})
                        elif content.type == PromptMessageContentType.IMAGE:
                            parsed = self._parse_data_uri(content.data)
                            if parsed:
                                media_type, base64_data = parsed
                                content_blocks.append(
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": media_type,
                                            "data": base64_data,
                                        },
                                    }
                                )
                    messages.append({"role": "user", "content": content_blocks or ""})
                else:
                    messages.append({"role": "user", "content": ""})
                continue

            if isinstance(message, AssistantPromptMessage):
                content_blocks: list[dict] = []
                if message.content:
                    content_blocks.append({"type": "text", "text": message.content})

                for tool_call in message.tool_calls or []:
                    arguments = tool_call.function.arguments or "{}"
                    try:
                        tool_input = json.loads(arguments)
                    except Exception:
                        tool_input = {"raw": arguments}

                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tool_call.id or "",
                            "name": tool_call.function.name or "",
                            "input": tool_input,
                        }
                    )

                messages.append(
                    {
                        "role": "assistant",
                        "content": content_blocks if content_blocks else "",
                    }
                )
                continue

            if isinstance(message, ToolPromptMessage):
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message.tool_call_id,
                                "content": message.content or "",
                            }
                        ],
                    }
                )
                continue

            raise ValueError(f"Unknown message type {type(message)}")

        system = "\n\n".join(part for part in system_parts if part).strip() or None
        return system, messages

    def _convert_tools_to_anthropic(self, tools: Sequence[PromptMessageTool]) -> list[dict]:
        """Convert Dify tools to Anthropic tool format."""
        return [
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.parameters or {"type": "object", "properties": {}},
            }
            for tool in tools
        ]

    def _prepare_anthropic_payload(
        self,
        model: str,
        prompt_messages: Sequence[PromptMessage],
        model_parameters: dict,
        tools: Optional[Sequence[PromptMessageTool]] = None,
        stop: Optional[Sequence[str]] = None,
        stream: bool = True,
    ) -> dict:
        """Prepare the request payload for Anthropic Messages API."""
        system, messages = self._convert_prompt_messages_to_anthropic(prompt_messages)

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "max_tokens": model_parameters.get("max_tokens", 512),
        }

        if system:
            payload["system"] = system

        if "temperature" in model_parameters:
            payload["temperature"] = model_parameters["temperature"]

        if "top_p" in model_parameters:
            payload["top_p"] = model_parameters["top_p"]

        if stop:
            payload["stop_sequences"] = list(stop)

        if tools:
            payload["tools"] = self._convert_tools_to_anthropic(tools)

        return payload

    def _post_json(self, url: str, headers: dict[str, str], payload: dict):
        """Send a POST request with JSON payload."""
        request = urllib_request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        return urllib_request.urlopen(request)

    def _raise_anthropic_http_error(self, ex: urllib_error.HTTPError):
        """Convert HTTP errors to Dify invoke errors."""
        try:
            body = ex.read().decode("utf-8")
        except Exception:
            body = str(ex)

        message = body or str(ex)

        if ex.code in {401, 403}:
            raise InvokeAuthorizationError(message)
        if ex.code >= 500:
            raise InvokeServerUnavailableError(message)
        raise InvokeBadRequestError(message)

    def _invoke_anthropic_foundry(
        self,
        model: str,
        credentials: dict,
        prompt_messages: Sequence[PromptMessage],
        model_parameters: dict,
        tools: Optional[Sequence[PromptMessageTool]] = None,
        stop: Optional[Sequence[str]] = None,
        stream: bool = True,
    ) -> Union[LLMResult, Generator]:
        """Invoke Azure Anthropic Foundry endpoint using Anthropic Messages API."""
        url = self._anthropic_messages_url(str(credentials.get("endpoint")))
        headers = {
            "content-type": "application/json",
            "x-api-key": str(credentials.get("api_key")),
            "anthropic-version": "2023-06-01",
        }
        payload = self._prepare_anthropic_payload(
            model=model,
            prompt_messages=prompt_messages,
            model_parameters=model_parameters,
            tools=tools,
            stop=stop,
            stream=stream,
        )

        try:
            response = self._post_json(url, headers, payload)
            if stream:
                return self._handle_anthropic_stream_response(
                    response=response,
                    model=model,
                    prompt_messages=prompt_messages,
                )
            body = json.loads(response.read().decode("utf-8"))
            return self._handle_anthropic_non_stream_response(
                response=body,
                model=model,
                prompt_messages=prompt_messages,
                credentials=credentials,
            )
        except urllib_error.HTTPError as ex:
            self._raise_anthropic_http_error(ex)
        except urllib_error.URLError as ex:
            raise InvokeConnectionError(str(ex)) from ex

    def _iter_sse_events(self, response) -> Generator[dict, None, None]:
        """Iterate over SSE events from the response."""
        event_name: str | None = None
        data_lines: list[str] = []

        def flush():
            nonlocal event_name, data_lines
            if not data_lines:
                event_name = None
                return None
            raw_data = "\n".join(data_lines).strip()
            event = event_name
            event_name = None
            data_lines = []
            if not raw_data or raw_data == "[DONE]":
                return None
            return {"event": event, "data": json.loads(raw_data)}

        for raw_line in response:
            line = raw_line.decode("utf-8").rstrip("\n")
            if not line.strip():
                item = flush()
                if item is not None:
                    yield item
                continue

            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())

        item = flush()
        if item is not None:
            yield item

    def _handle_anthropic_stream_response(
        self,
        response,
        model: str,
        prompt_messages: Sequence[PromptMessage],
    ) -> Generator:
        """Handle streaming response from Anthropic Messages API."""
        tool_buffers: dict[int, dict[str, Any]] = {}

        for item in self._iter_sse_events(response):
            data = item["data"]
            event_type = data.get("type") or item.get("event")

            if event_type == "error":
                message = data.get("error", {}).get("message", "Anthropic streaming error")
                raise InvokeBadRequestError(message)

            if event_type == "content_block_start":
                block = data.get("content_block", {})
                if block.get("type") == "tool_use":
                    tool_buffers[data.get("index", 0)] = {
                        "id": block.get("id", ""),
                        "name": block.get("name", ""),
                        "parts": [],
                    }
                continue

            if event_type == "content_block_delta":
                delta = data.get("delta", {})
                delta_type = delta.get("type")

                if delta_type == "text_delta" and delta.get("text"):
                    yield LLMResultChunk(
                        model=model,
                        prompt_messages=list(prompt_messages),
                        delta=LLMResultChunkDelta(
                            index=0,
                            message=AssistantPromptMessage(
                                content=delta["text"],
                                tool_calls=[],
                            ),
                        ),
                    )
                    continue

                if delta_type == "input_json_delta":
                    state = tool_buffers.setdefault(
                        data.get("index", 0),
                        {"id": "", "name": "", "parts": []},
                    )
                    state["parts"].append(delta.get("partial_json", ""))
                    continue

            if event_type == "content_block_stop":
                state = tool_buffers.pop(data.get("index", 0), None)
                if not state:
                    continue

                arguments = "".join(state["parts"]).strip() or "{}"
                yield LLMResultChunk(
                    model=model,
                    prompt_messages=list(prompt_messages),
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(
                            content="",
                            tool_calls=[
                                AssistantPromptMessage.ToolCall(
                                    id=state["id"],
                                    type="function",
                                    function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                        name=state["name"],
                                        arguments=arguments,
                                    ),
                                )
                            ],
                        ),
                    ),
                )

    def _handle_anthropic_non_stream_response(
        self,
        response: dict,
        model: str,
        prompt_messages: Sequence[PromptMessage],
        credentials: dict,
    ) -> LLMResult:
        """Handle non-streaming response from Anthropic Messages API."""
        text_parts: list[str] = []
        tool_calls: list[AssistantPromptMessage.ToolCall] = []

        for block in response.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    AssistantPromptMessage.ToolCall(
                        id=block.get("id", ""),
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=block.get("name", ""),
                            arguments=json.dumps(block.get("input", {})),
                        ),
                    )
                )

        usage = response.get("usage", {})
        assistant_prompt_message = AssistantPromptMessage(
            content="".join(text_parts),
            tool_calls=tool_calls,
        )
        return LLMResult(
            model=model,
            prompt_messages=list(prompt_messages),
            message=assistant_prompt_message,
            usage=self._calc_response_usage(
                model,
                credentials,
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
            ),
        )

    # =========================================================================
    # Main Invoke Method
    # =========================================================================

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
        endpoint = str(credentials.get("endpoint"))

        # Route to Anthropic Foundry if endpoint matches
        if self._is_anthropic_foundry_endpoint(endpoint):
            return self._invoke_anthropic_foundry(
                model=model,
                credentials=credentials,
                prompt_messages=prompt_messages,
                model_parameters=model_parameters,
                tools=tools,
                stop=stop,
                stream=stream,
            )

        # Standard Azure AI Studio flow
        if not self.client:
            api_key = str(credentials.get("api_key"))
            api_version = credentials.get("api_version", "2024-05-01-preview")

            self.client = ChatCompletionsClient(
                endpoint=endpoint,
                credential=AzureKeyCredential(api_key),
                api_version=api_version,
            )
        messages = [
            self._convert_prompt_message_to_dict(msg) for msg in prompt_messages
        ]
        optional_fields = {}
        # GPT O series model don't support max_tokens parameter
        if "max_tokens" in model_parameters:
            optional_fields["max_tokens"] = model_parameters["max_tokens"]
        payload = {
            "messages": messages,
            "temperature": model_parameters.get("temperature", 0),
            "top_p": model_parameters.get("top_p", 1),
            "stream": stream,
            "model": model,
            **optional_fields,
        }
        if stop:
            payload["stop"] = stop
        if tools:
            payload["tools"] = self._convert_tools(tools)
        try:
            response = self.client.complete(**payload)
            if stream:
                return self._handle_stream_response(response, model, prompt_messages)
            else:
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
            endpoint = str(credentials.get("endpoint"))

            # Validate Anthropic Foundry credentials
            if self._is_anthropic_foundry_endpoint(endpoint):
                payload = self._prepare_anthropic_payload(
                    model=model,
                    prompt_messages=[
                        UserPromptMessage(content="I say 'ping', you say 'pong'. ping")
                    ],
                    model_parameters={"max_tokens": 16},
                    stream=False,
                )
                response = self._post_json(
                    self._anthropic_messages_url(endpoint),
                    {
                        "content-type": "application/json",
                        "x-api-key": str(credentials.get("api_key")),
                        "anthropic-version": "2023-06-01",
                    },
                    payload,
                )
                json.loads(response.read().decode("utf-8"))
                return

            # Standard Azure AI Studio validation
            api_key = str(credentials.get("api_key"))
            api_version = credentials.get("api_version", "2024-05-01-preview")
            client = ChatCompletionsClient(
                endpoint=endpoint,
                credential=AzureKeyCredential(api_key),
                api_version=api_version,
            )
            client.complete(
                messages=[
                    {"role": "user", "content": "I say 'ping', you say 'pong'.ping"},
                ],
                model=model,
            )
        except urllib_error.HTTPError as ex:
            try:
                body = ex.read().decode("utf-8")
            except Exception:
                body = str(ex)
            raise CredentialsValidateFailedError(body)
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
            ],
        }

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        """
        Used to define customizable model schema
        """
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
                name="max_tokens",
                type=ParameterType.INT,
                use_template="max_tokens",
                min=1,
                default=512,
                label=I18nObject(zh_Hans="最大生成长度", en_US="Max Tokens"),
            ),
        ]

        # Add features based on credentials
        features = []
        if credentials.get("vision_support") == "true":
            features.append(ModelFeature.VISION)
        if credentials.get("function_call_support") == "true":
            features.append(ModelFeature.TOOL_CALL)
            features.append(ModelFeature.MULTI_TOOL_CALL)

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
