import base64
import copy
import io
import json
import logging
import math
from collections.abc import Generator, Sequence
from typing import Any, Optional, Union, cast

import tiktoken
from PIL import Image
from dify_plugin.entities.model import AIModelEntity, ModelPropertyKey
from dify_plugin.entities.model.llm import (
    LLMMode,
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
)
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    AudioPromptMessageContent,
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageFunction,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import CredentialsValidateFailedError
from dify_plugin.interfaces.model.large_language_model import LargeLanguageModel
from openai import AzureOpenAI, Stream
from openai.types import Completion
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessageToolCall,
)
from openai.types.chat.chat_completion_chunk import ChoiceDelta, ChoiceDeltaToolCall
from openai.types.responses import ResponseStreamEvent, Response

from ..common import _CommonAzureOpenAI
from ..constants import LLM_BASE_MODELS

logger = logging.getLogger(__name__)

THINKING_SERIES_COMPATIBILITY = ("o", "gpt-5")
CODE_SERIES_COMPATIBILITY = "gpt-5.1-codex-max"


class AzureOpenAILargeLanguageModel(_CommonAzureOpenAI, LargeLanguageModel):
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
        base_model_name = self._get_base_model_name(credentials)
        ai_model_entity = self._get_ai_model_entity(
            base_model_name=base_model_name, model=model
        )
        # gpt-5.1-codex-max uses Responses API
        if base_model_name.startswith(CODE_SERIES_COMPATIBILITY):
            return self._chat_generate_with_responses(
                model=model,
                credentials=credentials,
                prompt_messages=prompt_messages,
                model_parameters=model_parameters,
                tools=tools,
                stop=stop,
                stream=stream,
                user=user,
            )
        elif (
            ai_model_entity
            and ai_model_entity.entity.model_properties.get(ModelPropertyKey.MODE)
            == LLMMode.CHAT.value
        ):
            # Use the Responses API for GPT models (gpt-5 series)
            if base_model_name.startswith(("gpt-5-codex", "gpt-5.1-codex", "gpt-5-pro")):
                return self._chat_generate_with_responses(
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
            return self._generate(
                model=model,
                credentials=credentials,
                prompt_messages=prompt_messages,
                model_parameters=model_parameters,
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
        base_model_name = self._get_base_model_name(credentials)
        model_entity = self._get_ai_model_entity(
            base_model_name=base_model_name, model=model
        )
        if not model_entity:
            raise ValueError(f"Base Model Name {base_model_name} is invalid")
        model_mode = model_entity.entity.model_properties.get(ModelPropertyKey.MODE)
        if model_mode == LLMMode.CHAT.value:
            return self._num_tokens_from_messages(credentials, prompt_messages, tools)
        else:
            content = prompt_messages[0].content
            assert isinstance(content, str)
            return self._num_tokens_from_string(credentials, content)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        if "openai_api_base" not in credentials:
            raise CredentialsValidateFailedError(
                "Azure OpenAI API Base Endpoint is required"
            )

        # Check authentication method
        auth_method = credentials.get("auth_method", "api_key")
        if auth_method == "api_key" and "openai_api_key" not in credentials:
            raise CredentialsValidateFailedError(
                "Azure OpenAI API key is required when using API Key authentication"
            )

        if "base_model_name" not in credentials:
            raise CredentialsValidateFailedError("Base Model Name is required")
        base_model_name = self._get_base_model_name(credentials)
        ai_model_entity = self._get_ai_model_entity(
            base_model_name=base_model_name, model=model
        )
        if not ai_model_entity:
            raise CredentialsValidateFailedError(
                f"Base Model Name {credentials['base_model_name']} is invalid"
            )

        try:
            client = AzureOpenAI(**self._to_credential_kwargs(credentials))
            if (
                base_model_name.startswith(THINKING_SERIES_COMPATIBILITY)
                and CODE_SERIES_COMPATIBILITY not in base_model_name
            ):
                client.chat.completions.create(
                    messages=[{"role": "user", "content": "ping"}],
                    model=model,
                    temperature=1,
                    max_completion_tokens=20,
                    stream=False,
                )
            elif (
                ai_model_entity.entity.model_properties.get(ModelPropertyKey.MODE)
                == LLMMode.CHAT.value
            ):
                client.chat.completions.create(
                    messages=[{"role": "user", "content": "ping"}],
                    model=model,
                    temperature=0,
                    max_tokens=20,
                    stream=False,
                )
            elif base_model_name.startswith(CODE_SERIES_COMPATIBILITY):
                client.responses.create(
                    input="ping",
                    model=model,
                    stream=False,
                )
            else:
                client.completions.create(
                    prompt="ping",
                    model=model,
                    temperature=0,
                    max_tokens=20,
                    stream=False,
                )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        base_model_name = self._get_base_model_name(credentials)
        ai_model_entity = self._get_ai_model_entity(
            base_model_name=base_model_name, model=model
        )
        return ai_model_entity.entity if ai_model_entity else None

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
        client = AzureOpenAI(**self._to_credential_kwargs(credentials))
        extra_model_kwargs = {}
        if stop:
            extra_model_kwargs["stop"] = stop
        if user:
            extra_model_kwargs["user"] = user

        # client.completions does not support reasoning_effort
        if "reasoning_effort" in model_parameters:
            model_parameters.pop("reasoning_effort")
        response = client.completions.create(
            prompt=prompt_messages[0].content,
            model=model,
            stream=stream,
            **model_parameters,
            **extra_model_kwargs,
        )

        if stream:
            return self._handle_generate_stream_response(
                model, credentials, response, prompt_messages
            )
        return self._handle_generate_response(
            model, credentials, response, prompt_messages
        )

    def _handle_generate_response(
        self,
        model: str,
        credentials: dict,
        response: Completion,
        prompt_messages: list[PromptMessage],
    ):
        assistant_text = response.choices[0].text
        assistant_prompt_message = AssistantPromptMessage(content=assistant_text)
        if response.usage:
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
        else:
            content = prompt_messages[0].content
            assert isinstance(content, str)
            prompt_tokens = self._num_tokens_from_string(credentials, content)
            completion_tokens = self._num_tokens_from_string(
                credentials, assistant_text
            )
        usage = self._calc_response_usage(
            model, credentials, prompt_tokens, completion_tokens
        )
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
        full_text = ""

        for chunk in response:
            if len(chunk.choices) == 0:
                continue
            delta = chunk.choices[0]
            if delta.finish_reason is None and (delta.text is None or delta.text == ""):
                continue

            text = delta.text or ""
            assistant_prompt_message = AssistantPromptMessage(content=text)
            full_text += text
            if delta.finish_reason is not None:
                if chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens
                    completion_tokens = chunk.usage.completion_tokens
                else:
                    content = prompt_messages[0].content
                    assert isinstance(content, str)
                    prompt_tokens = self._num_tokens_from_string(credentials, content)
                    completion_tokens = self._num_tokens_from_string(
                        credentials, full_text
                    )
                usage = self._calc_response_usage(
                    model, credentials, prompt_tokens, completion_tokens
                )

                yield LLMResultChunk(
                    model=chunk.model,
                    prompt_messages=prompt_messages,
                    system_fingerprint=chunk.system_fingerprint,
                    delta=LLMResultChunkDelta(
                        index=delta.index,
                        message=assistant_prompt_message,
                        finish_reason=delta.finish_reason,
                        usage=usage,
                    ),
                )
            else:
                yield LLMResultChunk(
                    model=chunk.model,
                    prompt_messages=prompt_messages,
                    system_fingerprint=chunk.system_fingerprint,
                    delta=LLMResultChunkDelta(
                        index=delta.index, message=assistant_prompt_message
                    ),
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
        base_model_name = self._get_base_model_name(credentials)
        client = AzureOpenAI(**self._to_credential_kwargs(credentials))
        response_format = model_parameters.get("response_format")
        if response_format:
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
        extra_model_kwargs = {}
        if tools:
            extra_model_kwargs["tools"] = [
                PromptMessageFunction(function=tool).model_dump(mode="json")
                for tool in tools
            ]
        if stop:
            extra_model_kwargs["stop"] = stop
        if user:
            extra_model_kwargs["user"] = user
        if stream:
            extra_model_kwargs["stream_options"] = {"include_usage": True}
        prompt_messages = self._clear_illegal_prompt_messages(
            base_model_name, prompt_messages
        )
        block_as_stream = False
        if base_model_name.startswith(THINKING_SERIES_COMPATIBILITY):
            # o1 and o1-* do not support streaming
            # https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/reasoning#api--feature-support
            if base_model_name.startswith("o1"):
                if stream:
                    block_as_stream = True
                    stream = False
                    if "stream_options" in extra_model_kwargs:
                        del extra_model_kwargs["stream_options"]
            if "stop" in extra_model_kwargs:
                del extra_model_kwargs["stop"]

        messages: Any = [
            self._convert_prompt_message_to_dict(m) for m in prompt_messages
        ]
        if model_parameters.get('reasoning_effort') not in (None, 'none'):
            model_parameters.pop('temperature', None)
        response = client.chat.completions.create(
            messages=messages,
            model=model,
            stream=stream,
            **model_parameters,
            **extra_model_kwargs,
        )

        if stream:
            return self._handle_chat_generate_stream_response(
                model, credentials, response, prompt_messages, tools
            )
        block_result = self._handle_chat_generate_response(
            model, credentials, response, prompt_messages, tools
        )
        if block_as_stream:
            return self._handle_chat_block_as_stream_response(
                block_result, prompt_messages, stop
            )

        return block_result

    def _chat_generate_with_responses(
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
        Generate chat responses with the OpenAI Responses API.

        Reference: https://platform.openai.com/docs/guides/migrate-to-responses
        """
        client = AzureOpenAI(**self._to_credential_kwargs(credentials))

        # Convert prompt messages to the Responses API format
        input_messages = self._convert_prompt_messages_to_responses_input(prompt_messages)

        # Build parameters for the Responses API
        responses_params = {
            "model": model,
            "input": input_messages,
        }

        # Map model parameters to the Responses API
        if "temperature" in model_parameters:
            responses_params["temperature"] = model_parameters["temperature"]
        if "top_p" in model_parameters:
            responses_params["top_p"] = model_parameters["top_p"]
        if "max_tokens" in model_parameters:
            responses_params["max_output_tokens"] = model_parameters["max_tokens"]
        elif "max_completion_tokens" in model_parameters:
            responses_params["max_output_tokens"] = model_parameters["max_completion_tokens"]

        # Handle tools in the Responses API format
        if tools:
            responses_params["tools"] = []
            for tool in tools:
                # Ensure parameters are valid JSON objects
                parameters = tool.parameters
                if isinstance(parameters, str):
                    try:
                        parameters = json.loads(parameters)
                    except json.JSONDecodeError:
                        parameters = {"type": "object", "properties": {}}
                elif not isinstance(parameters, dict):
                    parameters = {"type": "object", "properties": {}}

                tool_dict = {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": parameters
                }
                responses_params["tools"].append(tool_dict)
            responses_params["tool_choice"] = "auto"

        # Handle the user identifier
        if user:
            responses_params["user"] = user

        # Handle stop sequences
        if stop:
            responses_params["stop"] = stop

        # Handle the response format
        response_format = model_parameters.get("response_format")
        if response_format:
            if response_format == "json_schema":
                json_schema_data = model_parameters.get("json_schema", {})
                # Ensure json_schema is an object rather than a string
                if isinstance(json_schema_data, str):
                    try:
                        json_schema_data = json.loads(json_schema_data)
                    except json.JSONDecodeError:
                        json_schema_data = {}

                responses_params["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": json_schema_data.get("name", "response"),
                        "strict": json_schema_data.get("strict", True),
                        "schema": json_schema_data.get("json_schema", {})
                    }
                }
            else:
                responses_params["text"] = {
                    "format": {"type": response_format}
                }

        if "reasoning_effort" in model_parameters:
            responses_params["reasoning"] = {"effort": model_parameters["reasoning_effort"]}

        logger.info(
            f"llm request with responses api: model={model}, stream={stream}, "
            f"parameters={responses_params}"
        )

        # Call the Responses API
        response = client.responses.create(
            **responses_params,
            stream=stream,
        )

        if stream:
            return self._handle_responses_stream_response(
                model, credentials, response, prompt_messages, tools
            )
        else:
            return self._handle_responses_response(
                model, credentials, response, prompt_messages, tools
            )

    def _convert_prompt_messages_to_responses_input(
        self, prompt_messages: list[PromptMessage]
    ) -> list[dict]:
        """Convert prompt messages to the Responses API input format."""
        input_messages = []

        for message in prompt_messages:
            if isinstance(message, SystemPromptMessage):
                input_messages.append({
                    "role": "developer",
                    "content": message.content
                })
            elif isinstance(message, UserPromptMessage):
                if isinstance(message.content, str):
                    input_messages.append({
                        "role": "user",
                        "content": message.content
                    })
                else:
                    # Handle multimodal content
                    content_parts = []
                    for content_item in message.content or []:
                        if content_item.type == PromptMessageContentType.TEXT:
                            text_content = cast(TextPromptMessageContent, content_item)
                            content_parts.append({
                                "type": "input_text",
                                "text": text_content.data
                            })
                        elif content_item.type == PromptMessageContentType.IMAGE:
                            image_content = cast(ImagePromptMessageContent, content_item)
                            image_part = {
                                "type": "input_image",
                            }
                            if image_content.url:
                                image_part["image_url"] = image_content.url
                            else:
                                image_part["image_url"] = image_content.data
                            if image_content.detail:
                                image_part["detail"] = image_content.detail.value
                            content_parts.append(image_part)

                    input_messages.append({
                        "role": "user",
                        "content": content_parts
                    })
            elif isinstance(message, AssistantPromptMessage):
                input_messages.append({
                    "role": "assistant",
                    "content": message.content
                })
            elif isinstance(message, ToolPromptMessage):
                input_messages.append({
                    "role": "assistant",  # Responses API represents tool calls with the assistant role
                    "content": message.content
                })

        return input_messages

    def _handle_responses_response(
        self,
        model: str,
        credentials: dict,
        response: Response,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> LLMResult:
        """Handle non-streaming Responses API responses."""
        # Extract text content
        content = ""

        # Inspect the actual response structure
        if hasattr(response, 'output') and response.output:
            # Standard Responses API format
            for item in response.output:
                item_type = getattr(item, 'type', '')
                if item_type == "message":
                    # message.content can be a string or a list of segments
                    item_content = getattr(item, 'content', None)
                    if isinstance(item_content, str):
                        if item_content:
                            content += item_content
                    elif isinstance(item_content, list):
                        for part in item_content:
                            part_type = getattr(part, 'type', '')
                            if part_type in ("output_text", "text", "input_text"):
                                text_val = getattr(part, 'text', '')
                                if text_val:
                                    content += text_val
                elif item_type in ("output_text", "text"):
                    # Some implementations return output_text/text entries directly
                    text_val = getattr(item, 'text', '')
                    if text_val:
                        content += text_val
        elif hasattr(response, 'text') and response.text:
            # Fallback format
            content = response.text
        elif hasattr(response, 'content') and response.content:
            # Direct content format
            content = response.content

        # Handle tool calls
        tool_calls = []
        if hasattr(response, 'output') and response.output:
            for item in response.output:
                item_type = getattr(item, 'type', '')
                if item_type == "function_call":
                    # Handle the Responses API tool call format
                    function_name = getattr(item, 'name', '')
                    function_args = getattr(item, 'arguments', '')
                    call_id = getattr(item, 'call_id', '') or getattr(item, 'id', '')

                    # Ensure the arguments are valid JSON strings
                    if isinstance(function_args, dict):
                        args_str = json.dumps(function_args)
                    elif isinstance(function_args, str):
                        args_str = function_args
                    else:
                        args_str = "{}"

                    tool_call = AssistantPromptMessage.ToolCall(
                        id=call_id,
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=function_name,
                            arguments=args_str
                        )
                    )
                    tool_calls.append(tool_call)

        assistant_prompt_message = AssistantPromptMessage(
            content=content,
            tool_calls=tool_calls
        )

        # Calculate token usage
        prompt_tokens = 0
        completion_tokens = 0
        prompt_tokens_details: Optional[dict] = None
        completion_tokens_details: Optional[dict] = None

        if hasattr(response, 'usage') and response.usage:
            usage_obj = response.usage
            # Support Responses API usage fields
            prompt_tokens = getattr(usage_obj, 'input_tokens', None) or getattr(usage_obj, 'prompt_tokens', 0)
            completion_tokens = getattr(usage_obj, 'output_tokens', None) or getattr(usage_obj, 'completion_tokens', 0)
            # Support implementations that expose detailed fields (convert SDK types to dict)
            # Prefer the unified prompt_tokens_details/completion_tokens_details fields
            if hasattr(usage_obj, 'prompt_tokens_details') and usage_obj.prompt_tokens_details:
                _ptd = usage_obj.prompt_tokens_details
                if hasattr(_ptd, 'to_dict'):
                    prompt_tokens_details = _ptd.to_dict()
                elif isinstance(_ptd, dict):
                    prompt_tokens_details = _ptd
                else:
                    prompt_tokens_details = {
                        'cached_tokens': getattr(_ptd, 'cached_tokens', None)
                    }
            elif hasattr(usage_obj, 'input_tokens_details') and usage_obj.input_tokens_details:
                it = usage_obj.input_tokens_details
                if hasattr(it, 'to_dict'):
                    prompt_tokens_details = it.to_dict()
                else:
                    prompt_tokens_details = {
                        'cached_tokens': getattr(it, 'cached_tokens', None)
                    }
            if hasattr(usage_obj, 'completion_tokens_details') and usage_obj.completion_tokens_details:
                completion_tokens_details = usage_obj.completion_tokens_details
            elif hasattr(usage_obj, 'output_tokens_details') and usage_obj.output_tokens_details:
                ot = usage_obj.output_tokens_details
                if hasattr(ot, 'to_dict'):
                    completion_tokens_details = ot.to_dict()
                else:
                    completion_tokens_details = {
                        'reasoning_tokens': getattr(ot, 'reasoning_tokens', None)
                    }
        else:
            # Estimate usage when it is not provided
            prompt_tokens = self._num_tokens_from_messages(
                credentials, prompt_messages, tools
            )
            completion_tokens = self._num_tokens_from_messages(
                credentials, [assistant_prompt_message]
            )

        usage = self._calc_response_usage(
            model, credentials, prompt_tokens, completion_tokens,
            prompt_tokens_details=prompt_tokens_details,
            completion_tokens_details=completion_tokens_details
        )

        return LLMResult(
            model=model,
            prompt_messages=prompt_messages,
            message=assistant_prompt_message,
            usage=usage,
            system_fingerprint=getattr(response, 'id', ''),
        )

    def _handle_responses_stream_response(
        self,
        model: str,
        credentials: dict,
        response: Stream[ResponseStreamEvent],
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> Generator:
        """Handle streaming Responses API responses."""
        full_text = ""
        tool_calls = []
        index = 0
        is_first = True

        # Track tool call state
        pending_tool_calls = {}  # call_id -> tool_call_dict
        current_tool_call = None

        for chunk in response:
            if is_first:
                is_first = False

            # Handle the Responses API streaming event format
            chunk_type = getattr(chunk, 'type', '')

            if chunk_type == 'response.output_text.delta':
                # ResponseTextDeltaEvent format - text delta
                delta_text = getattr(chunk, 'delta', '')
                if delta_text:
                    full_text += delta_text

                    assistant_prompt_message = AssistantPromptMessage(
                        content=delta_text,
                        tool_calls=[]
                    )

                    yield LLMResultChunk(
                        model=model,
                        prompt_messages=prompt_messages,
                        system_fingerprint=getattr(chunk, 'item_id', ''),
                        delta=LLMResultChunkDelta(
                            index=index,
                            message=assistant_prompt_message
                        ),
                    )
                    index += 1

            elif chunk_type == 'response.output_item.added':
                # ResponseOutputItemAddedEvent format - tool call start
                item = getattr(chunk, 'item', None)
                if item and hasattr(item, 'type'):
                    item_type = getattr(item, 'type', '')

                    if item_type == 'function_call':
                        # Tool call start - initialize the tool call object
                        function_name = getattr(item, 'name', '')
                        call_id = getattr(item, 'call_id', '')

                        if function_name and call_id:
                            pending_tool_calls[call_id] = {
                                'id': call_id,
                                'name': function_name,
                                'arguments': ''  # Start empty and wait for argument deltas
                            }
                            current_tool_call = call_id

            elif chunk_type == 'response.function_call_arguments.delta':
                # ResponseFunctionCallArgumentsDeltaEvent format - tool argument delta
                delta_args = getattr(chunk, 'delta', '')

                # Use the currently tracked tool call
                if current_tool_call and current_tool_call in pending_tool_calls:
                    # Append arguments to the existing tool call
                    pending_tool_calls[current_tool_call]['arguments'] += delta_args

            elif chunk_type == 'response.function_call_arguments.done':
                # ResponseFunctionCallArgumentsDoneEvent format - tool arguments complete
                call_id = getattr(chunk, 'item_id', '')
                final_args = getattr(chunk, 'arguments', '')

                if call_id and call_id in pending_tool_calls:
                    # Update the tool call with the completed arguments
                    pending_tool_calls[call_id]['arguments'] = final_args

            elif chunk_type == 'response.output_item.done':
                # ResponseOutputItemDoneEvent format - tool call complete
                item = getattr(chunk, 'item', None)
                if item and hasattr(item, 'type'):
                    item_type = getattr(item, 'type', '')

                    if item_type == 'function_call':
                        # Tool call complete - emit the full tool call
                        function_name = getattr(item, 'name', '')
                        function_args = getattr(item, 'arguments', '')
                        call_id = getattr(item, 'call_id', '')

                        # Prefer the completed arguments (from response.function_call_arguments.done)
                        if call_id in pending_tool_calls:
                            final_args = pending_tool_calls[call_id]['arguments'] or function_args
                        else:
                            final_args = function_args

                        if function_name:
                            tool_call = AssistantPromptMessage.ToolCall(
                                id=call_id,
                                type="function",
                                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                    name=function_name,
                                    arguments=final_args or "{}"
                                )
                            )

                            assistant_prompt_message = AssistantPromptMessage(
                                content="",
                                tool_calls=[tool_call]
                            )

                            yield LLMResultChunk(
                                model=model,
                                prompt_messages=prompt_messages,
                                system_fingerprint=call_id,
                                delta=LLMResultChunkDelta(
                                    index=index,
                                    message=assistant_prompt_message
                                ),
                            )
                            index += 1

                            # Clean up completed tool calls
                            if call_id in pending_tool_calls:
                                del pending_tool_calls[call_id]

                            # Reset tracking for the current tool call
                            if call_id == current_tool_call:
                                current_tool_call = None

            elif hasattr(chunk, 'delta') and hasattr(chunk.delta, 'text'):
                # Handle alternative formats
                delta_text = chunk.delta.text or ""
                if delta_text:
                    full_text += delta_text

                    assistant_prompt_message = AssistantPromptMessage(
                        content=delta_text,
                        tool_calls=[]
                    )

                    yield LLMResultChunk(
                        model=model,
                        prompt_messages=prompt_messages,
                        system_fingerprint=getattr(chunk, 'item_id', ''),
                        delta=LLMResultChunkDelta(
                            index=index,
                            message=assistant_prompt_message
                        ),
                    )
                    index += 1

        # Handle the final usage statistics
        prompt_tokens = self._num_tokens_from_messages(
            credentials, prompt_messages, tools
        )
        full_assistant_prompt_message = AssistantPromptMessage(content=full_text)
        completion_tokens = self._num_tokens_from_messages(
            credentials, [full_assistant_prompt_message]
        )

        usage = self._calc_response_usage(
            model, credentials, prompt_tokens, completion_tokens
        )

        yield LLMResultChunk(
            model=model,
            prompt_messages=prompt_messages,
            system_fingerprint="",
            delta=LLMResultChunkDelta(
                index=index,
                message=AssistantPromptMessage(content=""),
                finish_reason="stop",
                usage=usage,
            ),
        )

    def _handle_chat_block_as_stream_response(
        self,
        block_result: LLMResult,
        prompt_messages: list[PromptMessage],
        stop: Optional[list[str]] = None,
    ) -> Generator[LLMResultChunk, None, None]:
        """
        Handle llm chat response

        :param model: model name
        :param credentials: credentials
        :param response: response
        :param prompt_messages: prompt messages
        :param tools: tools for tool calling
        :param stop: stop words
        :return: llm response chunk generator
        """
        text = block_result.message.content
        text = cast(str, text)
        if stop:
            text = self.enforce_stop_tokens(text, stop)
        yield LLMResultChunk(
            model=block_result.model,
            prompt_messages=prompt_messages,
            system_fingerprint=block_result.system_fingerprint,
            delta=LLMResultChunkDelta(
                index=0,
                message=AssistantPromptMessage(
                    content=text or "",
                    name=block_result.message.name,
                    tool_calls=block_result.message.tool_calls,
                ),
                finish_reason="stop",
                usage=block_result.usage,
            ),
        )

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
        if model.startswith(("o1", "o3", "o4")):
            system_message_count = len(
                [m for m in prompt_messages if isinstance(m, SystemPromptMessage)]
            )
            if system_message_count > 0:
                new_prompt_messages = []
                for prompt_message in prompt_messages:
                    if isinstance(prompt_message, SystemPromptMessage):
                        prompt_message = UserPromptMessage(
                            content=prompt_message.content, name=prompt_message.name
                        )
                    new_prompt_messages.append(prompt_message)
                prompt_messages = new_prompt_messages
        return prompt_messages

    def _handle_chat_generate_response(
        self,
        model: str,
        credentials: dict,
        response: ChatCompletion,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ):
        assistant_message = response.choices[0].message
        assistant_message_tool_calls = assistant_message.tool_calls
        tool_calls = []
        self._update_tool_calls(
            tool_calls=tool_calls, tool_calls_response=assistant_message_tool_calls
        )
        content = ""
        if hasattr(
            assistant_message, "model_extra"
        ) and assistant_message.model_extra.get("reasoning_content"):
            content += (
                "<think>\n"
                + assistant_message.model_extra["reasoning_content"]
                + "\n</think>"
            )
        content += assistant_message.content

        assistant_prompt_message = AssistantPromptMessage(
            content=content, tool_calls=tool_calls
        )
        if response.usage:
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
        else:
            prompt_tokens = self._num_tokens_from_messages(
                credentials, prompt_messages, tools
            )
            completion_tokens = self._num_tokens_from_messages(
                credentials, [assistant_prompt_message]
            )
        usage = self._calc_response_usage(
            model, credentials, prompt_tokens, completion_tokens
        )
        result = LLMResult(
            model=response.model or model,
            prompt_messages=prompt_messages,
            message=assistant_prompt_message,
            usage=usage,
            system_fingerprint=response.system_fingerprint,
        )
        return result

    def _handle_chat_generate_stream_response(
        self,
        model: str,
        credentials: dict,
        response: Stream[ChatCompletionChunk],
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ):
        is_reasoning = False
        index = 0
        real_model = model
        system_fingerprint = None
        completion = ""
        tool_calls = []
        prompt_tokens = 0
        completion_tokens = 0
        has_usage = False
        for chunk in response:
            if len(chunk.choices) == 0:
                if chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens
                    completion_tokens = chunk.usage.completion_tokens
                    has_usage = True
                continue
            delta = chunk.choices[0]
            if delta.delta is None:
                continue
            self._update_tool_calls(
                tool_calls=tool_calls, tool_calls_response=delta.delta.tool_calls
            )
            if (
                delta.finish_reason is None
                and not delta.delta.content
                and not hasattr(delta.delta, "reasoning_content")
            ):
                continue
            content, is_reasoning = self._azure_wrap_thinking_by_reasoning_content(
                delta.delta, is_reasoning
            )
            assistant_prompt_message = AssistantPromptMessage(
                content=content, tool_calls=tool_calls
            )
            real_model = chunk.model
            system_fingerprint = chunk.system_fingerprint
            completion += content
            yield LLMResultChunk(
                model=real_model,
                prompt_messages=prompt_messages,
                system_fingerprint=system_fingerprint,
                delta=LLMResultChunkDelta(
                    index=index, message=assistant_prompt_message
                ),
            )
            index += 1
        if not has_usage:
            prompt_tokens = self._num_tokens_from_messages(
                credentials, prompt_messages, tools
            )
            full_assistant_prompt_message = AssistantPromptMessage(content=completion)
            completion_tokens = self._num_tokens_from_messages(
                credentials, [full_assistant_prompt_message]
            )
        usage = self._calc_response_usage(
            model, credentials, prompt_tokens, completion_tokens
        )

        yield LLMResultChunk(
            model=real_model,
            prompt_messages=prompt_messages,
            system_fingerprint=system_fingerprint,
            delta=LLMResultChunkDelta(
                index=index,
                message=AssistantPromptMessage(content=""),
                finish_reason="stop",
                usage=usage,
            ),
        )

    @staticmethod
    def _update_tool_calls(
        tool_calls: list[AssistantPromptMessage.ToolCall],
        tool_calls_response: Optional[
            Sequence[ChatCompletionMessageToolCall | ChoiceDeltaToolCall]
        ],
    ) -> None:
        if tool_calls_response:
            for response_tool_call in tool_calls_response:
                if isinstance(response_tool_call, ChatCompletionMessageToolCall):
                    function = AssistantPromptMessage.ToolCall.ToolCallFunction(
                        name=response_tool_call.function.name,
                        arguments=response_tool_call.function.arguments,
                    )
                    tool_call = AssistantPromptMessage.ToolCall(
                        id=response_tool_call.id,
                        type=response_tool_call.type,
                        function=function,
                    )
                    tool_calls.append(tool_call)
                elif isinstance(response_tool_call, ChoiceDeltaToolCall):
                    index = response_tool_call.index
                    if index < len(tool_calls):
                        tool_calls[index].id = (
                            response_tool_call.id or tool_calls[index].id
                        )
                        tool_calls[index].type = (
                            response_tool_call.type or tool_calls[index].type
                        )
                        if response_tool_call.function:
                            tool_calls[index].function.name = (
                                response_tool_call.function.name
                                or tool_calls[index].function.name
                            )
                            tool_calls[index].function.arguments += (
                                response_tool_call.function.arguments or ""
                            )
                    else:
                        assert response_tool_call.id is not None
                        assert response_tool_call.type is not None
                        assert response_tool_call.function is not None
                        assert response_tool_call.function.name is not None
                        assert response_tool_call.function.arguments is not None
                        function = AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=response_tool_call.function.name,
                            arguments=response_tool_call.function.arguments,
                        )
                        tool_call = AssistantPromptMessage.ToolCall(
                            id=response_tool_call.id,
                            type=response_tool_call.type,
                            function=function,
                        )
                        tool_calls.append(tool_call)

    @staticmethod
    def _convert_prompt_message_to_dict(message: PromptMessage):
        if isinstance(message, UserPromptMessage):
            message = cast(UserPromptMessage, message)
            if isinstance(message.content, str):
                message_dict = {"role": "user", "content": message.content}
            else:
                sub_messages = []
                assert message.content is not None
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
                    elif message_content.type == PromptMessageContentType.AUDIO:
                        message_content = cast(
                            AudioPromptMessageContent, message_content
                        )
                        sub_message_dict = {
                            "type": "input_audio",
                            "input_audio": {
                                "data": message_content.base64_data,
                                "format": message_content.format,
                            },
                        }
                        sub_messages.append(sub_message_dict)
                message_dict = {"role": "user", "content": sub_messages}
        elif isinstance(message, AssistantPromptMessage):
            message_dict = {"role": "assistant", "content": message.content}
            if message.tool_calls:
                message_dict["tool_calls"] = [
                    tool_call.model_dump(mode="json")
                    for tool_call in message.tool_calls
                ]
        elif isinstance(message, SystemPromptMessage):
            message = cast(SystemPromptMessage, message)
            message_dict = {"role": "system", "content": message.content}
        elif isinstance(message, ToolPromptMessage):
            message = cast(ToolPromptMessage, message)
            message_dict = {
                "role": "tool",
                "name": message.name,
                "content": message.content,
                "tool_call_id": message.tool_call_id,
            }
        else:
            raise ValueError(f"Got unknown type {message}")
        if message.name:
            message_dict["name"] = message.name
        return message_dict

    def _num_tokens_from_string(
        self,
        credentials: dict,
        text: str,
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        try:
            encoding = tiktoken.encoding_for_model(credentials["base_model_name"])
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")
        num_tokens = len(encoding.encode(text))
        if tools:
            num_tokens += self._num_tokens_for_tools(encoding, tools)
        return num_tokens

    def _num_tokens_from_messages(
        self,
        credentials: dict,
        messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        """Calculate num tokens for gpt-3.5-turbo and gpt-4 with tiktoken package.

        Official documentation: https://github.com/openai/openai-cookbook/blob/
        main/examples/How_to_format_inputs_to_ChatGPT_models.ipynb"""
        model = credentials["base_model_name"]
        if model.startswith(("o1", "o3", "o4", "gpt-4.1", "gpt-4.5", "gpt-5")):
            model = "gpt-4o"
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            logger.warning("Warning: model not found. Using cl100k_base encoding.")
            encoding_name = "cl100k_base"
            encoding = tiktoken.get_encoding(encoding_name)
        if model.startswith("gpt-35-turbo-0301"):
            tokens_per_message = 4
            tokens_per_name = -1
        elif (
            model.startswith("gpt-35-turbo")
            or model.startswith("gpt-4")
            or model.startswith(("o1", "o3", "o4"))
            or model.startswith("grok")
        ):
            tokens_per_message = 3
            tokens_per_name = 1
        else:
            raise NotImplementedError(
                f"get_num_tokens_from_messages() is not presently implemented for model {model}.See https://github.com/openai/openai-python/blob/main/chatml.md for information on how messages are converted to tokens."
            )
        num_tokens = 0
        messages_dict = [self._convert_prompt_message_to_dict(m) for m in messages]
        image_details: list[dict] = []
        for message in messages_dict:
            num_tokens += tokens_per_message
            for key, value in message.items():
                if isinstance(value, list):
                    text = ""
                    for item in value:
                        if isinstance(item, dict):
                            if item["type"] == "text":
                                text += item["text"]
                            elif item["type"] == "image_url":
                                image_details.append(item["image_url"])
                    value = text
                if key == "tool_calls":
                    for tool_call in value:
                        assert isinstance(tool_call, dict)
                        for t_key, t_value in tool_call.items():
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
        num_tokens += 3
        if tools:
            num_tokens += self._num_tokens_for_tools(encoding, tools)
        if len(image_details) > 0:
            num_tokens += self._num_tokens_from_images(
                image_details=image_details,
                base_model_name=credentials["base_model_name"],
            )
        return num_tokens

    @staticmethod
    def _num_tokens_for_tools(
        encoding: tiktoken.Encoding, tools: list[PromptMessageTool]
    ) -> int:
        num_tokens = 0
        for tool in tools:
            num_tokens += len(encoding.encode("type"))
            num_tokens += len(encoding.encode("function"))
            num_tokens += len(encoding.encode("name"))
            num_tokens += len(encoding.encode(tool.name))
            num_tokens += len(encoding.encode("description"))
            num_tokens += len(encoding.encode(tool.description))
            parameters = tool.parameters
            num_tokens += len(encoding.encode("parameters"))
            if "title" in parameters:
                num_tokens += len(encoding.encode("title"))
                num_tokens += len(encoding.encode(parameters["title"]))
            num_tokens += len(encoding.encode("type"))
            num_tokens += len(encoding.encode(parameters["type"]))
            if "properties" in parameters:
                num_tokens += len(encoding.encode("properties"))
                for key, value in parameters["properties"].items():
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

    @staticmethod
    def _get_ai_model_entity(base_model_name: str, model: str):
        for ai_model_entity in LLM_BASE_MODELS:
            if ai_model_entity.base_model_name == base_model_name:
                ai_model_entity_copy = copy.deepcopy(ai_model_entity)
                ai_model_entity_copy.entity.model = model
                ai_model_entity_copy.entity.label.en_US = model
                ai_model_entity_copy.entity.label.zh_Hans = model
                return ai_model_entity_copy

    def _get_base_model_name(self, credentials: dict) -> str:
        base_model_name = credentials.get("base_model_name")
        if not base_model_name:
            raise ValueError("Base Model Name is required")
        return base_model_name

    def _get_image_patches(self, n: int) -> float:
        return (n + 32 - 1) // 32

    # This algorithm is based on https://platform.openai.com/docs/guides/images-vision?api-mode=chat#calculating-costs
    def _num_tokens_from_images(
        self, base_model_name: str, image_details: list[dict]
    ) -> int:
        num_tokens: int = 0
        base_tokens: int = 0
        tile_tokens: int = 0

        if base_model_name.startswith("gpt-4o-mini"):
            base_tokens = 2833
            tile_tokens = 5667
        elif base_model_name.startswith(("gpt-4o", "gpt-4.1", "gpt-4.5")):
            base_tokens = 85
            tile_tokens = 170
        elif base_model_name.startswith(("o1", "o3", "o1-pro")):
            base_tokens = 75
            tile_tokens = 150

        for image_detail in image_details:
            base64_str = image_detail["url"].split(",")[1]

            image_data = base64.b64decode(base64_str)
            image = Image.open(io.BytesIO(image_data))
            width, height = image.size

            if base_model_name.startswith(("gpt-4.1-mini", "gpt-4.1-nano", "o4-mini")):
                width_patches = self._get_image_patches(width)
                height_patches = self._get_image_patches(height)
                cap = 1536

                tokens = width_patches * height_patches

                if tokens > cap:
                    shrink_factor = math.sqrt(cap * 32**2 / (width * height))

                    new_width = width * shrink_factor
                    new_height = height * shrink_factor

                    w_patches = int(new_width / 32)
                    h_patches = int(new_height / 32)

                    tokens = w_patches * h_patches

                if base_model_name.startswith("o4-mini"):
                    num_tokens += int(tokens * 1.72)
                elif base_model_name.startswith("gpt-4.1-nano"):
                    num_tokens += int(tokens * 2.46)
                elif base_model_name.startswith("gpt-4.1-mini"):
                    num_tokens += int(tokens * 1.62)
            else:
                if image_detail["detail"] == "low":
                    # Regardless of input size, low detail images are a fixed cost.
                    num_tokens += 85
                else:
                    # Scale the image longest side to 2048px
                    if width > 2048 or height > 2048:
                        aspect_ratio = width / height
                        if aspect_ratio > 1:
                            width, height = 2048, int(2048 / aspect_ratio)
                        else:
                            width, height = int(2048 * aspect_ratio), 2048

                    # Further scale the image shortest side to 768px
                    if width >= height and height > 768:
                        width, height = int((768 / height) * width), 768
                    elif height > width and width > 768:
                        width, height = 768, int((768 / width) * height)

                    # Calculate the number of tiles
                    w_tiles = math.ceil(width / 512)
                    h_tiles = math.ceil(height / 512)
                    total_tiles = w_tiles * h_tiles

                    num_tokens += base_tokens + total_tiles * tile_tokens

        return num_tokens

    @staticmethod
    def _azure_wrap_thinking_by_reasoning_content(
        delta: ChoiceDelta, is_reasoning: bool
    ) -> tuple[str, bool]:
        """
        If the reasoning response is from delta.get("reasoning_content"), we wrap
        it with HTML think tag.
        :param delta: delta dictionary from LLM streaming response
        :param is_reasoning: is reasoning
        :return: tuple of (processed_content, is_reasoning)
        """

        content = delta.content or ""
        reasoning_content = (
            delta.reasoning_content if hasattr(delta, "reasoning_content") else ""
        )
        try:
            if reasoning_content:
                try:
                    if not is_reasoning:
                        content = "<think>\n" + reasoning_content
                        is_reasoning = True
                    else:
                        content = reasoning_content
                except Exception as ex:
                    raise ValueError(
                        f"[_azure_wrap_thinking_by_reasoning_content-1] {ex}"
                    ) from ex
            elif is_reasoning and content:
                content = "\n</think>" + content
                is_reasoning = False
        except Exception as ex:
            raise ValueError(
                f"[_azure_wrap_thinking_by_reasoning_content-2] {ex}"
            ) from ex
        return content, is_reasoning
