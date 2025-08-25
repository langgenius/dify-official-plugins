import base64
import io
import json
import re
import copy
from collections.abc import Generator, Sequence
from typing import Any, Mapping, Optional, Union, cast
import logging

import anthropic
import requests
from anthropic import Anthropic, Stream
from anthropic.types import (
    ContentBlockDeltaEvent,
    Message,
    MessageDeltaEvent,
    MessageStartEvent,
    MessageStopEvent,
    MessageStreamEvent,
    completion_create_params,
)
from dify_plugin.entities.model.llm import (
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
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
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
from httpx import Timeout
from PIL import Image

ANTHROPIC_BLOCK_MODE_PROMPT = 'You should always follow the instructions and output a valid {{block}} object.\nThe structure of the {{block}} object you can found in the instructions, use {"answer": "$your_answer"} as the default structure\nif you are not sure about the structure.\n\n<instructions>\n{{instructions}}\n</instructions>\n'


class PromptCachingHandler:
    def __init__(self, prompt_messages: Sequence[PromptMessage], enable_system_cache: bool = False):
        self.prompt_messages = prompt_messages
        self.enable_system_cache = enable_system_cache

    def get_system_prompt(self) -> Union[str, list[dict]]:
        system_components = []
        raw_system_content_parts = []
        for message in self.prompt_messages:
            if isinstance(message, SystemPromptMessage):
                if isinstance(message.content, str):
                    raw_system_content_parts.append(message.content.strip())
                elif isinstance(message.content, list):
                    for c in message.content:
                        if isinstance(c, TextPromptMessageContent):
                            raw_system_content_parts.append(c.data.strip())
                else:
                    raise ValueError(
                        f"Unknown system prompt message content type {type(message.content)}"
                    )

        system_content_str = "\n".join(raw_system_content_parts)

        if self.enable_system_cache and "<cache>" in system_content_str:
            parts = re.split(r'(<cache>.*?</cache>)', system_content_str, flags=re.DOTALL)
            for part in parts:
                if not part:
                    continue
                if part.startswith('<cache>') and part.endswith('</cache>'):
                    cached_content = part[len('<cache>'):-len('</cache>')]
                    if cached_content:
                        system_components.append({
                "type": "text",
                            "text": cached_content,
                "cache_control": {"type": "ephemeral"}
                        })
                elif part:
                    system_components.append({
                        "type": "text",
                        "text": part
                    })
        elif system_content_str:
            system_components.append({"type": "text", "text": system_content_str})

        system: Union[str, list[dict]] = ""
        if system_components:
            if any("cache_control" in comp for comp in system_components):
                system = system_components
            else:
                system = "\n".join(comp["text"] for comp in system_components if comp.get("text"))
        
        return system

    # --- Pricing Helpers -------------------------------------------------
    # Cache write incurs a 25% premium (1.25×) on the written tokens
    # Cache read receives a 90% discount (0.1×) on the read tokens

    CACHE_WRITE_MULTIPLIER: float = 1.25
    CACHE_READ_MULTIPLIER: float = 0.1

    @classmethod
    def calc_adjusted_prompt_tokens(
        cls,
        base_prompt_tokens: int,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
    ) -> int:
        """Return billing-adjusted prompt tokens.

        Args:
            base_prompt_tokens: The raw prompt tokens counted by the API.
            cache_creation_input_tokens: Tokens written to cache in this request.
            cache_read_input_tokens: Tokens read from cache in this request.
        Returns:
            int: Adjusted prompt tokens to be billed.
        """
        adjusted = base_prompt_tokens

        if cache_creation_input_tokens > 0:
            adjusted += int(cache_creation_input_tokens * cls.CACHE_WRITE_MULTIPLIER)

        if cache_read_input_tokens > 0:
            adjusted += int(cache_read_input_tokens * cls.CACHE_READ_MULTIPLIER)

        return adjusted


class AnthropicLargeLanguageModel(LargeLanguageModel):
    def __init__(self, model_schemas=None):
        super().__init__(model_schemas or [])
        self.previous_thinking_blocks = []
        self.previous_redacted_thinking_blocks = []
        # Flag to indicate whether tool definitions should include cache_control
        self._tool_cache_enabled = False
        self._system_cache_enabled = False
        self._image_cache_enabled = False
        self._document_cache_enabled = False
        self._tool_results_cache_enabled = False
        self._message_flow_cache_threshold: int = 0

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
        *,
        model: str,
        credentials: Mapping[str, Any],
        prompt_messages: Sequence[PromptMessage],
        model_parameters: Mapping[str, Any],
        tools: Optional[list[PromptMessageTool]] = None,
        stop: Optional[Sequence[str]] = None,
        stream: bool = True,
        user: Optional[str] = None,
    ) -> Union[LLMResult, Generator]:
        model_parameters = dict(model_parameters)
        extra_model_kwargs = {}
        extra_headers = {}

        credentials_kwargs = self._to_credential_kwargs(credentials)
        client = Anthropic(**credentials_kwargs)

        if "max_tokens_to_sample" in model_parameters:
            model_parameters["max_tokens"] = model_parameters.pop(
                "max_tokens_to_sample"
            )

        thinking = model_parameters.pop("thinking", False)
        thinking_budget = model_parameters.pop("thinking_budget", 1024)
        context_1m = model_parameters.pop("context_1m", False)
        
        if thinking:
            extra_model_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget
            }
            for key in ("temperature", "top_p", "top_k"):
                model_parameters.pop(key, None)

        if context_1m:
            if "anthropic-beta" in extra_headers:
                extra_headers["anthropic-beta"] += ",context-1m-2025-08-07"
            else:
                extra_headers["anthropic-beta"] = "context-1m-2025-08-07"

        if model_parameters.get("extended_output", False):
            model_parameters.pop("extended_output", None)
            if "anthropic-beta" in extra_headers:
                extra_headers["anthropic-beta"] += ",output-128k-2025-02-19"
            else:
                extra_headers["anthropic-beta"] = "output-128k-2025-02-19"

        if model == "claude-3-7-sonnet-20250219" and tools:
            if "anthropic-beta" in extra_headers:
                extra_headers["anthropic-beta"] += ",token-efficient-tools-2025-02-19"
            else:
                extra_headers["anthropic-beta"] = "token-efficient-tools-2025-02-19"

        if stop:
            extra_model_kwargs["stop_sequences"] = stop
        if user:
            extra_model_kwargs["metadata"] = completion_create_params.Metadata(
                user_id=user
            )
        # Extract caching flags early so _convert_prompt_messages can use them
        self._tool_cache_enabled = model_parameters.pop("prompt_caching_tool_definitions", False)
        self._system_cache_enabled = model_parameters.pop("prompt_caching_system_message", False)
        self._image_cache_enabled = model_parameters.pop("prompt_caching_images", False)
        self._document_cache_enabled = model_parameters.pop("prompt_caching_documents", False)
        self._tool_results_cache_enabled = model_parameters.pop("prompt_caching_tool_results", False)
        self._message_flow_cache_threshold = int(model_parameters.pop("prompt_caching_message_flow", 0) or 0)

        (system, prompt_message_dicts) = self._convert_prompt_messages(prompt_messages)
        if system:
            extra_model_kwargs["system"] = system

        # Helper to prune cache_control blocks to max 4 by priority
        def _prune_cache_blocks(payload: dict):
            blocks: list[tuple[int, int, dict]] = []  # (priority, neg_length, block_dict)

            # Helper to record
            def _record_block(d: dict, priority: int, length: int = 0):
                if "cache_control" in d:
                    blocks.append((priority, -length, d))

            # 1. system blocks
            if isinstance(payload.get("system"), list):
                for block in payload["system"]:
                    if isinstance(block, dict):
                        text_len = 0
                        if block.get("type") == "text":
                            text_len = len(block.get("text", ""))
                        _record_block(block, 2, text_len)  # system priority 2

            # 2. message content blocks
            for msg in payload.get("messages", []):
                content = msg.get("content")
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        text_len = 0
                        if btype in {"image", "document"}:
                            pr = 1
                            if block.get("source", {}).get("type") == "base64":
                                text_len = len(block.get("source", {}).get("data", ""))
                        elif btype in {"tool_use", "tool_result"}:
                            pr = 4
                        else:
                            pr = 3  # text or others
                            if btype == "text":
                                text_len = len(block.get("text", ""))
                        _record_block(block, pr, text_len)

            # 3. tools definitions
            for tool_def in payload.get("tools", []):
                if isinstance(tool_def, dict):
                    _record_block(tool_def, 4, 0)

            # Sort by priority (lower number = higher priority), then by length descending
            blocks.sort(key=lambda x: (x[0], x[1]))

            logging.info(f"Blocks: {blocks}")

            # Keep first 4
            for idx, (_, _, block_dict) in enumerate(blocks):
                if idx >= 4:
                    block_dict.pop("cache_control", None)

        def _sanitize_for_logging(data_structure: Any) -> Any:
            """Recursively truncate 'data' fields in a nested structure for logging."""
            if isinstance(data_structure, dict):
                loggable_data = copy.deepcopy(data_structure)
                for key, value in loggable_data.items():
                    if key == 'data' and isinstance(value, str) and len(value) > 50:
                        loggable_data[key] = f"{value[:50]}...[truncated]"
                    else:
                        loggable_data[key] = _sanitize_for_logging(value)
                return loggable_data
            elif isinstance(data_structure, list):
                return [_sanitize_for_logging(item) for item in data_structure]
            else:
                return data_structure

        # Build preliminary request payload (without tools yet)
        request_payload = {
            "model": model,
            "messages": prompt_message_dicts,
            "stream": stream,
            "extra_headers": extra_headers,
            **model_parameters,
            **extra_model_kwargs,
        }

        # We will insert tools later; prune cache blocks after that just before send

        if model == "claude-3-5-sonnet-20240620":
            if model_parameters.get("max_tokens", 0) > 4096:
                extra_headers["anthropic-beta"] = "max-tokens-3-5-sonnet-2024-07-15"
        if any(
            (
                isinstance(content, DocumentPromptMessageContent)
                for prompt_message in prompt_messages
                if isinstance(prompt_message.content, list)
                for content in prompt_message.content
            )
        ):
            if "anthropic-beta" in extra_headers:
                extra_headers["anthropic-beta"] += ",pdfs-2024-09-25"
            else:
                extra_headers["anthropic-beta"] = "pdfs-2024-09-25"

        if not any(isinstance(msg, ToolPromptMessage) for msg in prompt_messages):
            self.previous_thinking_blocks = []
            self.previous_redacted_thinking_blocks = []

        if tools:
            extra_model_kwargs["tools"] = [
                self._transform_tool_prompt(tool) for tool in tools
            ]
            
            # Log the transformed tools to verify cache_control is added
            logging.info(f"Anthropic API Tools: {json.dumps(extra_model_kwargs['tools'], indent=2)}")
            
            request_payload["tools"] = extra_model_kwargs["tools"]

            # Now prune cache blocks to respect Anthropic limit
            _prune_cache_blocks(request_payload)

            loggable_request = _sanitize_for_logging(request_payload)
            logging.info(f"Anthropic API Request: {json.dumps(loggable_request, indent=2)}")
            response = client.messages.create(
                model=model,
                messages=prompt_message_dicts,
                stream=stream,
                extra_headers=extra_headers,
                tools=extra_model_kwargs["tools"],
                **model_parameters,
                **{k: v for k, v in extra_model_kwargs.items() if k != "tools"},
            )
        else:
            _prune_cache_blocks(request_payload)

            loggable_request = _sanitize_for_logging(request_payload)
            logging.info(f"Anthropic API Request: {json.dumps(loggable_request, indent=2)}")
            response = client.messages.create(
                model=model,
                messages=prompt_message_dicts,
                stream=stream,
                extra_headers=extra_headers,
                **model_parameters,
                **extra_model_kwargs,
            )

        if stream:
            return self._handle_chat_generate_stream_response(
                model, credentials, response, prompt_messages
            )
        
        logging.info(f"Anthropic API Response: {response.model_dump_json(indent=2)}")
        return self._handle_chat_generate_response(
            model, credentials, response, prompt_messages
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
        if model_parameters.get("response_format"):
            stop = stop or []
            self._transform_chat_json_prompts(
                model=model,
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
            model,
            credentials,
            prompt_messages,
            model_parameters,
            tools,
            stop,
            stream,
            user,
        )

    def _transform_tool_prompt(self, tool: PromptMessageTool) -> dict:
        """
        Transform tool prompt to Anthropic-compatible format, ensuring it matches JSON Schema draft 2020-12
        
        This method handles:
        1. Converting custom types to JSON Schema standard types
        2. Mapping options arrays to enum arrays
        3. Ensuring schema validity for Anthropic API requirements
        
        Args:
            tool: The tool prompt message with parameters to transform
            
        Returns:
            dict: A tool definition compatible with Anthropic API
        """
        # Make a deep copy to avoid modifying the original
        input_schema = json.loads(json.dumps(tool.parameters))
        
        # Fix any non-standard types in properties
        if 'properties' in input_schema:
            for _, prop_config in input_schema['properties'].items():
                # Handle 'select' type conversion
                if prop_config.get('type') == 'select':
                    prop_config['type'] = 'string'
                    
                    # Convert 'options' to 'enum' if needed
                    if 'options' in prop_config and 'enum' not in prop_config:
                        enum_values = [option.get('value') for option in prop_config['options'] 
                                      if 'value' in option]
                        prop_config['enum'] = enum_values
                    
                    # Handle case with neither options nor enum
                    if 'enum' not in prop_config:
                        if 'default' in prop_config:
                            default_value = prop_config['default']
                            prop_config['enum'] = [default_value]
                        else:
                            # Rather than creating an empty enum that will fail validation,
                            # set a more appropriate default
                            prop_config['enum'] = [""]
        
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": input_schema,
            **({"cache_control": {"type": "ephemeral"}} if getattr(self, "_tool_cache_enabled", False) else {}),
        }

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
        if "```\n" not in stop:
            stop.append("```\n")
        if "\n```" not in stop:
            stop.append("\n```")
        if len(prompt_messages) > 0 and isinstance(
            prompt_messages[0], SystemPromptMessage
        ):
            prompt_messages[0] = SystemPromptMessage(
                content=ANTHROPIC_BLOCK_MODE_PROMPT.replace(
                    "{{instructions}}", prompt_messages[0].content
                ).replace("{{block}}", response_format)
            )
            prompt_messages.append(
                AssistantPromptMessage(content=f"\n```{response_format}")
            )
        else:
            prompt_messages.insert(
                0,
                SystemPromptMessage(
                    content=ANTHROPIC_BLOCK_MODE_PROMPT.replace(
                        "{{instructions}}",
                        f"Please output a valid {response_format} object.",
                    ).replace("{{block}}", response_format)
                ),
            )
            prompt_messages.append(
                AssistantPromptMessage(content=f"\n```{response_format}")
            )

    def get_num_tokens(
        self,
        model: str,
        credentials: Mapping[str, Any],
        prompt_messages: Sequence[PromptMessage],
        tools: Optional[Sequence[PromptMessageTool]] = None,
    ) -> int:
        """
        Get number of tokens for given prompt messages

        :param model: model name
        :param credentials: model credentials
        :param prompt_messages: prompt messages
        :param tools: tools for tool calling
        :return:
        """
        credentials_kwargs = self._to_credential_kwargs(credentials)
        client = Anthropic(**credentials_kwargs)
        
        (system, prompt_message_dicts) = self._convert_prompt_messages(prompt_messages)
        
        if not prompt_message_dicts:
            prompt_message_dicts.append({"role": "user", "content": "Hello"})
        
        count_tokens_args = {
            "model": model,
            "messages": prompt_message_dicts
        }
        
        has_thinking_blocks = False
        for msg in prompt_message_dicts:
            if msg.get("role") == "assistant" and isinstance(msg.get("content"), list):
                for content_item in msg.get("content", []):
                    if isinstance(content_item, dict) and content_item.get("type") in ["thinking", "redacted_thinking"]:
                        has_thinking_blocks = True
                        break
            if has_thinking_blocks:
                break
        
        if has_thinking_blocks:
            count_tokens_args["thinking"] = {
                "type": "enabled",
                "budget_tokens": 4096
            }
        
        if system:
            count_tokens_args["system"] = system
        
        if tools:
            count_tokens_args["tools"] = [
                self._transform_tool_prompt(tool) for tool in tools
            ]
            
        response = client.messages.count_tokens(**count_tokens_args)
        return response.input_tokens

    def validate_credentials(self, model: str, credentials: Mapping) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            self._chat_generate(
                model=model,
                credentials=credentials,
                prompt_messages=[UserPromptMessage(content="ping")],
                model_parameters={"temperature": 0, "max_tokens": 20},
                stream=False,
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _handle_chat_generate_response(
        self,
        model: str,
        credentials: Mapping[str, Any],
        response: Message,
        prompt_messages: Sequence[PromptMessage],
    ) -> LLMResult:
        """
        Handle llm chat response with cache token adjustments for billing

        :param model: model name
        :param credentials: credentials
        :param response: response
        :param prompt_messages: prompt messages
        :return: llm response
        """
        self.previous_thinking_blocks = []
        self.previous_redacted_thinking_blocks = []
        
        assistant_prompt_message = AssistantPromptMessage(content="", tool_calls=[])
        
        for content in response.content:
            if content.type == "thinking":
                self.previous_thinking_blocks.append(content)
            elif content.type == "redacted_thinking":
                self.previous_redacted_thinking_blocks.append(content)
            elif content.type == "text" and isinstance(
                assistant_prompt_message.content, str
            ):
                assistant_prompt_message.content += content.text
            elif content.type == "tool_use":
                tool_call = AssistantPromptMessage.ToolCall(
                    id=content.id,
                    type="function",
                    function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                        name=content.name, arguments=json.dumps(content.input)
                    ),
                )
                assistant_prompt_message.tool_calls.append(tool_call)
        
        prompt_tokens = (
            response.usage
            and response.usage.input_tokens
            or self.get_num_tokens(
                model=model, credentials=credentials, prompt_messages=prompt_messages
            )
        )
        completion_tokens = (
            response.usage
            and response.usage.output_tokens
            or self.get_num_tokens(
                model=model,
                credentials=credentials,
                prompt_messages=[assistant_prompt_message],
            )
        )
        
        # Adjust prompt tokens for cache operations
        cache_creation_input_tokens = 0
        cache_read_input_tokens = 0
        if response.usage:
            if hasattr(response.usage, "cache_creation_input_tokens") and response.usage.cache_creation_input_tokens:
                cache_creation_input_tokens = response.usage.cache_creation_input_tokens
            if hasattr(response.usage, "cache_read_input_tokens") and response.usage.cache_read_input_tokens:
                cache_read_input_tokens = response.usage.cache_read_input_tokens

        adjusted_prompt_tokens = PromptCachingHandler.calc_adjusted_prompt_tokens(
            prompt_tokens,
            cache_creation_input_tokens,
            cache_read_input_tokens,
        )

        usage = super()._calc_response_usage(
            model=model,
            credentials=credentials,
            prompt_tokens=adjusted_prompt_tokens,
            completion_tokens=completion_tokens
        )
        
        result = LLMResult(
            model=response.model,
            prompt_messages=list(prompt_messages),
            message=assistant_prompt_message,
            usage=usage,
        )
        return result



    def _handle_chat_generate_stream_response(
        self,
        model: str,
        credentials: Mapping[str, Any],
        response: Stream[MessageStreamEvent],
        prompt_messages: Sequence[PromptMessage],
    ) -> Generator:
        """
        Handle llm chat stream response with token adjustments for caching
        """
        full_assistant_content = ""
        return_model = ""
        input_tokens = 0
        output_tokens = 0
        finish_reason = None
        index = 0
        tool_calls: list[AssistantPromptMessage.ToolCall] = []
        current_block_type = None
        current_block_index = None
        
        current_tool_name = None
        current_tool_id = None
        current_tool_params = ""
        
        if not any(isinstance(msg, ToolPromptMessage) for msg in prompt_messages):
            self.previous_thinking_blocks = []
            self.previous_redacted_thinking_blocks = []
            
        current_thinking_blocks = []
        current_redacted_thinking_blocks = []
        
        # Cache token tracking
        cache_creation_input_tokens = 0
        cache_read_input_tokens = 0
        
        for chunk in response:
            logging.info(f"Anthropic API Stream Response Chunk: {chunk.model_dump_json()}")
            if isinstance(chunk, MessageStartEvent):
                if chunk.message:
                    return_model = chunk.message.model
                    input_tokens = chunk.message.usage.input_tokens
                    if hasattr(chunk.message.usage, "cache_creation_input_tokens") and chunk.message.usage.cache_creation_input_tokens:
                        cache_creation_input_tokens = chunk.message.usage.cache_creation_input_tokens
                    if hasattr(chunk.message.usage, "cache_read_input_tokens") and chunk.message.usage.cache_read_input_tokens:
                        cache_read_input_tokens = chunk.message.usage.cache_read_input_tokens
            elif hasattr(chunk, "type") and chunk.type == "content_block_start":
                if hasattr(chunk, "content_block"):
                    content_block = chunk.content_block
                    
                    if getattr(content_block, 'type', None) == "tool_use":
                        current_tool_name = getattr(content_block, 'name', None)
                        current_tool_id = getattr(content_block, 'id', None)
                        
                        if current_tool_name and current_tool_id:
                            tool_call = AssistantPromptMessage.ToolCall(
                                id=current_tool_id,
                                type="function",
                                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                    name=current_tool_name, arguments=""
                                ),
                            )
                            
                            tool_calls.append(tool_call)
                    elif getattr(content_block, 'type', None) == "thinking":
                        current_thinking_blocks.append({
                            "type": "thinking",
                            "thinking": "",
                            "signature": ""
                        })
                    elif getattr(content_block, 'type', None) == "redacted_thinking":
                        current_redacted_thinking_blocks.append({
                            "type": "redacted_thinking"
                        })
            elif isinstance(chunk, ContentBlockDeltaEvent):
                if hasattr(chunk.delta, "type") and chunk.delta.type == "input_json_delta":
                    if hasattr(chunk.delta, "partial_json"):
                        partial_json = chunk.delta.partial_json
                        if partial_json:
                            current_tool_params += partial_json
                            
                            for tc in tool_calls:
                                if tc.id == current_tool_id:
                                    tc.function.arguments = current_tool_params
                                    break
                
                if chunk.index != current_block_index:
                    if current_block_type == "thinking" and current_block_index is not None:
                        assistant_prompt_message = AssistantPromptMessage(content="\n</think>")
                        yield LLMResultChunk(
                            model=return_model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=current_block_index, message=assistant_prompt_message
                            ),
                        )
                    
                    current_block_index = chunk.index
                    if hasattr(chunk.delta, "thinking"):
                        current_block_type = "thinking"
                        assistant_prompt_message = AssistantPromptMessage(content="<think>\n")
                        yield LLMResultChunk(
                            model=return_model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=chunk.index, message=assistant_prompt_message
                            ),
                        )
                    elif hasattr(chunk.delta, "text"):
                        current_block_type = "text"
                    elif hasattr(chunk.delta, "type") and chunk.delta.type == "redacted_thinking":
                        current_block_type = "redacted_thinking"
                        assistant_prompt_message = AssistantPromptMessage(content="<think>\n")
                        yield LLMResultChunk(
                            model=return_model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=chunk.index, message=assistant_prompt_message
                            ),
                        )
                
                if hasattr(chunk.delta, "thinking"):
                    thinking_text = chunk.delta.thinking or ""
                    full_assistant_content += thinking_text
                    
                    if current_thinking_blocks:
                        current_thinking_blocks[-1]["thinking"] += thinking_text
                    
                    assistant_prompt_message = AssistantPromptMessage(content=thinking_text)
                    index = chunk.index
                    yield LLMResultChunk(
                        model=return_model,
                        prompt_messages=prompt_messages,
                        delta=LLMResultChunkDelta(
                            index=chunk.index, message=assistant_prompt_message
                        ),
                    )
                elif hasattr(chunk.delta, "signature"):
                    if current_thinking_blocks:
                        current_thinking_blocks[-1]["signature"] = chunk.delta.signature
                elif hasattr(chunk.delta, "type") and chunk.delta.type == "redacted_thinking":
                    redacted_msg = "[Some of Claude's thinking was automatically encrypted for safety reasons]"
                    full_assistant_content += redacted_msg
                    assistant_prompt_message = AssistantPromptMessage(content=redacted_msg)
                    index = chunk.index
                    yield LLMResultChunk(
                        model=return_model,
                        prompt_messages=prompt_messages,
                        delta=LLMResultChunkDelta(
                            index=chunk.index, message=assistant_prompt_message
                        ),
                    )
                elif hasattr(chunk.delta, "text"):
                    chunk_text = chunk.delta.text or ""
                    full_assistant_content += chunk_text
                    assistant_prompt_message = AssistantPromptMessage(content=chunk_text)
                    index = chunk.index
                    yield LLMResultChunk(
                        model=return_model,
                        prompt_messages=prompt_messages,
                        delta=LLMResultChunkDelta(
                            index=chunk.index, message=assistant_prompt_message
                        ),
                    )
            elif isinstance(chunk, MessageDeltaEvent):
                output_tokens = chunk.usage.output_tokens
                finish_reason = chunk.delta.stop_reason
                if hasattr(chunk.usage, "cache_creation_input_tokens") and chunk.usage.cache_creation_input_tokens:
                    cache_creation_input_tokens = chunk.usage.cache_creation_input_tokens
                if hasattr(chunk.usage, "cache_read_input_tokens") and chunk.usage.cache_read_input_tokens:
                    cache_read_input_tokens = chunk.usage.cache_read_input_tokens
            elif isinstance(chunk, MessageStopEvent):
                if current_block_type == "thinking" and current_block_index is not None:
                    assistant_prompt_message = AssistantPromptMessage(content="\n</think>")
                    yield LLMResultChunk(
                        model=return_model,
                        prompt_messages=prompt_messages,
                        delta=LLMResultChunkDelta(
                            index=current_block_index, message=assistant_prompt_message
                        ),
                    )
                
                if current_tool_name and current_tool_id and current_tool_params and not tool_calls:
                    fallback_tool_call = AssistantPromptMessage.ToolCall(
                        id=current_tool_id,
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=current_tool_name, arguments=current_tool_params
                        ),
                    )
                    tool_calls.append(fallback_tool_call)
                
                if tool_calls and current_thinking_blocks:
                    self.previous_thinking_blocks = current_thinking_blocks
                if tool_calls and current_redacted_thinking_blocks:
                    self.previous_redacted_thinking_blocks = current_redacted_thinking_blocks
                
                # Adjust prompt tokens for cache operations
                adjusted_prompt_tokens = PromptCachingHandler.calc_adjusted_prompt_tokens(
                    input_tokens,
                    cache_creation_input_tokens,
                    cache_read_input_tokens,
                )
                
                usage = super()._calc_response_usage(
                    model, 
                    credentials, 
                    adjusted_prompt_tokens,
                    output_tokens
                )
                
                for tool_call in tool_calls:
                    if not tool_call.function.arguments:
                        tool_call.function.arguments = "{}"
                yield LLMResultChunk(
                    model=return_model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=index + 1,
                        message=AssistantPromptMessage(
                            content="", tool_calls=tool_calls
                        ),
                        finish_reason=finish_reason,
                        usage=usage,
                    ),
                )

    def _to_credential_kwargs(
        self, credentials: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """
        Transform credentials to kwargs for model instance

        :param credentials:
        :return:
        """
        credentials_kwargs = {
            "api_key": credentials["anthropic_api_key"],
            "timeout": Timeout(315.0, read=300.0, write=10.0, connect=5.0),
            "max_retries": 1,
        }
        api_url = credentials.get("anthropic_api_url")
        if api_url:
            credentials_kwargs["base_url"] = api_url.rstrip("/")
        return credentials_kwargs

    def _convert_prompt_messages(
        self, prompt_messages: Sequence[PromptMessage]
    ) -> tuple[Union[str, list[dict]], list[dict]]:
        """Convert prompt messages to dict list and system.
        
        This method processes different message types using a dispatch pattern,
        making the code more maintainable and following Fluent Python principles.
        """
        caching_handler = PromptCachingHandler(
            prompt_messages, 
            enable_system_cache=self._system_cache_enabled
        )
        system = caching_handler.get_system_prompt()
        
        # Find the last user message index
        last_user_msg_index = -1
        for i in range(len(prompt_messages) - 1, -1, -1):
            if isinstance(prompt_messages[i], UserPromptMessage):
                last_user_msg_index = i
                break
        
        
        # Process messages using list comprehension with dispatch
        prompt_message_dicts = []
        for i, message in enumerate(prompt_messages):
            if not isinstance(message, SystemPromptMessage):
                is_last_user_message = (
                    isinstance(message, UserPromptMessage) and 
                    i == last_user_msg_index
                )
                for message_dict in self._process_message(message, prompt_messages, is_last_user_message):
                    prompt_message_dicts.append(message_dict)
        
        # Merge consecutive assistant messages
        return system, self._merge_consecutive_assistant_messages(prompt_message_dicts)
    
    def _process_message(
        self, 
        message: PromptMessage, 
        all_messages: Sequence[PromptMessage],
        is_last_user_message: bool = False
    ) -> list[dict]:
        """Process a single message and return list of message dicts.
        
        Uses single-dispatch pattern for extensibility.
        """
        # Dispatch based on message type
        if isinstance(message, UserPromptMessage):
            return [self._process_user_message(message, is_last_user_message)]
        elif isinstance(message, AssistantPromptMessage):
            return [self._process_assistant_message(message, all_messages)]
        elif isinstance(message, ToolPromptMessage):
            return [self._process_tool_message(message)]
        else:
            raise ValueError(f"Unknown message type: {type(message).__name__}")
    
    def _process_user_message(self, message: UserPromptMessage, is_last_user_message: bool = False) -> dict:
        """Process user message into API format."""
        if isinstance(message.content, str):
            return self._create_user_text_message(message.content)
        
        # Process content list
        content_parts = self._process_user_content_list(message.content or [], is_last_user_message)
        return {"role": "user", "content": content_parts}
    
    def _create_user_text_message(self, text: str) -> dict:
        """Create user message dict with optional caching."""
        if self._should_cache_text(text):
            return {
                "role": "user",
                "content": [{
                    "type": "text",
                    "text": text,
                    "cache_control": {"type": "ephemeral"}
                }]
            }
        return {"role": "user", "content": text}
    
    def _process_user_content_list(self, content_list: list, is_last_user_message: bool = False) -> list[dict]:
        """Process list of content items, maintaining order."""
        # Group content by type for proper ordering
        content_groups: dict[str, list[dict[str, Any]]] = {
            'document': [],
            'image': [],
            'text': []
        }
        
        for content in content_list:
            if content.type == PromptMessageContentType.TEXT:
                content_groups['text'].append(
                    self._create_text_content(cast(TextPromptMessageContent, content))
                )
            elif content.type == PromptMessageContentType.IMAGE:
                content_groups['image'].append(
                    self._create_image_content(cast(ImagePromptMessageContent, content))
                )
            elif isinstance(content, DocumentPromptMessageContent):
                content_groups['document'].append(
                    self._create_document_content(content, is_last_user_message)
                )
        
        # Combine in the correct order: documents, images, text
        return (
            content_groups['document'] + 
            content_groups['image'] + 
            content_groups['text']
        )
    
    def _create_text_content(self, content: TextPromptMessageContent) -> dict:
        """Create text content dict with optional caching."""
        result: dict[str, Any] = {
            "type": "text",
            "text": content.data
        }
        if self._should_cache_text(content.data):
            result["cache_control"] = {"type": "ephemeral"}
        return result
    
    def _create_image_content(self, content: ImagePromptMessageContent) -> dict:
        """Create image content dict with base64 encoding."""
        mime_type, base64_data = self._process_image_data(content.data)
        
        # Validate mime type
        allowed_types = {"image/jpeg", "image/png", "image/gif", "image/webp"}
        if mime_type not in allowed_types:
            raise ValueError(
                f"Unsupported image type {mime_type}. "
                f"Allowed types: {', '.join(allowed_types)}"
            )
        
        result = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": base64_data
            }
        }
        
        if self._image_cache_enabled:
            result["cache_control"] = {"type": "ephemeral"}
        
        return result
    
    def _process_image_data(self, data: str) -> tuple[str, str]:
        """Process image data from URL or data URI."""
        if data.startswith("data:"):
            # Extract from data URI
            header, encoded = data.split(";base64,", 1)
            mime_type = header.replace("data:", "")
            return mime_type, encoded
        
        # Fetch from URL
        try:
            response = requests.get(data)
            response.raise_for_status()
            
            with Image.open(io.BytesIO(response.content)) as img:
                img_format = img.format or "jpeg"  # Default to jpeg if format is None
                mime_type = f"image/{img_format.lower()}"
            
            base64_data = base64.b64encode(response.content).decode("utf-8")
            return mime_type, base64_data
            
        except Exception as ex:
            raise ValueError(f"Failed to fetch image from {data}: {ex}") from ex
    
    def _create_document_content(self, content: DocumentPromptMessageContent, is_last_user_message: bool = False) -> dict:
        """Create document content dict."""
        if content.mime_type != "application/pdf":
            # If this is from the last user message, raise an error
            if is_last_user_message:
                raise ValueError(
                    f"Unsupported document type {content.mime_type}. "
                    "Only application/pdf is supported."
                )
            # Otherwise, replace with a text description
            else:
                # Extract filename if available from content metadata
                filename = getattr(content, 'filename', 'document')
                return {
                    "type": "text",
                    "text": f"[Unsupported document: {filename} ({content.mime_type})]"
                }
        
        result = {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": content.mime_type,
                "data": content.base64_data
            }
        }
        
        if self._document_cache_enabled:
            result["cache_control"] = {"type": "ephemeral"}
        
        return result
    
    def _process_assistant_message(
        self, 
        message: AssistantPromptMessage,
        all_messages: Sequence[PromptMessage]
    ) -> dict:
        """Process assistant message into API format."""
        content = []
        
        # Check if we need to include thinking blocks
        has_tool_messages = any(
            isinstance(msg, ToolPromptMessage) for msg in all_messages
        )
        
        if has_tool_messages:
            content.extend(self.previous_thinking_blocks)
            content.extend(self.previous_redacted_thinking_blocks)
        
        # Process tool calls or content
        if message.tool_calls:
            content.extend(
                self._create_tool_use_content(tool_call)
                for tool_call in message.tool_calls
            )
        elif message.content:
            if isinstance(message.content, str):
                content.append(self._create_assistant_text_content(message.content))
        
        return {"role": "assistant", "content": content}
    
    def _create_tool_use_content(self, tool_call: AssistantPromptMessage.ToolCall) -> dict:
        """Create tool use content dict."""
        result = {
            "type": "tool_use",
            "id": tool_call.id,
            "name": tool_call.function.name,
            "input": json.loads(tool_call.function.arguments)
        }
        
        if self._tool_results_cache_enabled:
            result["cache_control"] = {"type": "ephemeral"}
        
        return result
    
    def _create_assistant_text_content(self, text: str) -> dict:
        """Create assistant text content with optional caching."""
        if self._should_cache_text(text):
            return {
                "type": "text",
                "text": text,
                "cache_control": {"type": "ephemeral"}
            }
        return {"type": "text", "text": text}
    
    def _process_tool_message(self, message: ToolPromptMessage) -> dict:
        """Process tool result message."""
        tool_result_content = {
            "type": "tool_result",
            "tool_use_id": message.tool_call_id,
            "content": message.content
        }
        
        if self._tool_results_cache_enabled:
            tool_result_content["cache_control"] = {"type": "ephemeral"}
        
        return {
            "role": "user",
            "content": [tool_result_content]
        }
    
    def _should_cache_text(self, text: str) -> bool:
        """Determine if text should be cached based on word count."""
        return (
            self._message_flow_cache_threshold > 0 and
            len(text.split()) >= self._message_flow_cache_threshold
        )
    
    def _merge_consecutive_assistant_messages(self, messages: list[dict]) -> list[dict]:
        """Merge consecutive assistant messages to avoid API errors."""
        if not messages:
            return messages
        
        merged: list[dict] = []
        for message in messages:
            if (
                merged and 
                merged[-1]["role"] == "assistant" and 
                message["role"] == "assistant"
            ):
                # Merge content
                merged[-1]["content"].extend(message["content"])
            else:
                merged.append(message)
        
        return merged

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
            message_text = f"{human_prompt} {content}"
            if not isinstance(message.content, list):
                message_text = f"{ai_prompt} {content}"
            else:
                message_text = ""
                for sub_message in message.content:
                    if sub_message.type == PromptMessageContentType.TEXT:
                        message_text += f"{human_prompt} {sub_message.data}"
                    elif sub_message.type == PromptMessageContentType.IMAGE:
                        message_text += f"{human_prompt} [IMAGE]"
        elif isinstance(message, AssistantPromptMessage):
            if isinstance(message.content, list):
                message_text = ""
                for sub_message in message.content:
                    if sub_message.type == PromptMessageContentType.TEXT:
                        message_text += f"{ai_prompt} {sub_message.data}"
                    elif sub_message.type == PromptMessageContentType.IMAGE:
                        message_text += f"{ai_prompt} [IMAGE]"
            else:
                message_text = f"{ai_prompt} {content}"
        elif isinstance(message, SystemPromptMessage):
            if isinstance(content, str):
                message_text = content
            else:
                message_text = str(content)
        elif isinstance(message, ToolPromptMessage):
            message_text = f"{human_prompt} {message.content}"
        else:
            raise ValueError(f"Got unknown type {message}")
        return message_text

    def _convert_messages_to_prompt_anthropic(
        self, messages: Sequence[PromptMessage]
    ) -> str:
        """
        Format a list of messages into a full prompt for the Anthropic model

        :param messages: List of PromptMessage to combine.
        :return: Combined string with necessary human_prompt and ai_prompt tags.
        """
        if not messages:
            return ""
        messages = list(messages)
        if not isinstance(messages[-1], AssistantPromptMessage):
            messages.append(AssistantPromptMessage(content=""))
        text = "".join(
            (self._convert_one_message_to_text(message) for message in messages)
        )
        return text.rstrip()

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
            InvokeConnectionError: [
                anthropic.APIConnectionError,
                anthropic.APITimeoutError,
            ],
            InvokeServerUnavailableError: [anthropic.InternalServerError],
            InvokeRateLimitError: [anthropic.RateLimitError],
            InvokeAuthorizationError: [
                anthropic.AuthenticationError,
                anthropic.PermissionDeniedError,
            ],
            InvokeBadRequestError: [
                anthropic.BadRequestError,
                anthropic.NotFoundError,
                anthropic.UnprocessableEntityError,
                anthropic.APIError,
            ],
        }
