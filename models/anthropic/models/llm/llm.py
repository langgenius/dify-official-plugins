import base64
import io
import json
from collections.abc import Generator, Sequence
from typing import Any, Mapping, Optional, Union, cast
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


class AnthropicLargeLanguageModel(LargeLanguageModel):
    def __init__(self, model_schemas=None):
        super().__init__(model_schemas or [])
        self.previous_thinking_blocks = []
        self.previous_redacted_thinking_blocks = []

    def _process_text_for_cache(self, text):
        """
        Process text content to detect <cache> tags and return the appropriate 
        content format with cache_control if needed.
        
        :param text: Text content to process
        :return: Processed content, either as string or dict with cache_control
        """
        if "<cache>" in text:
            return {
                "type": "text",
                "text": text.replace("<cache>", ""),
                "cache_control": {"type": "ephemeral"}
            }
        return {"type": "text", "text": text}



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
        
        if thinking:
            extra_model_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget
            }
            for key in ("temperature", "top_p", "top_k"):
                model_parameters.pop(key, None)

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
        (system, prompt_message_dicts) = self._convert_prompt_messages(prompt_messages)
        if system:
            extra_model_kwargs["system"] = system

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
                
        # Extract cache metrics if available
        cache_creation_input_tokens = 0
        cache_read_input_tokens = 0
        if response.usage:
            if hasattr(response.usage, "cache_creation_input_tokens"):
                cache_creation_input_tokens = response.usage.cache_creation_input_tokens
            
            if hasattr(response.usage, "cache_read_input_tokens"):
                cache_read_input_tokens = response.usage.cache_read_input_tokens
        
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
        
        # UPDATED: Token accounting for billing with cache adjustments
        adjusted_prompt_tokens = prompt_tokens
        
        # Cache write premium: add full cache tokens plus 25% premium
        if cache_creation_input_tokens > 0:
            cache_write_premium = int(cache_creation_input_tokens * 0.25)
            adjusted_prompt_tokens += cache_creation_input_tokens + cache_write_premium
        
        # Cache read discount: only charge 10% of cached tokens (90% discount)
        if cache_read_input_tokens > 0:
            adjusted_prompt_tokens += int(cache_read_input_tokens * 0.1)
        
        # Get usage with adjusted token count for billing
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
        
        # Add cache token tracking
        cache_creation_input_tokens = 0
        cache_read_input_tokens = 0
        
        for chunk in response:
            if isinstance(chunk, MessageStartEvent):
                if chunk.message:
                    return_model = chunk.message.model
                    input_tokens = chunk.message.usage.input_tokens
                    # Check for cache metrics in the start event
                    if hasattr(chunk.message.usage, "cache_creation_input_tokens"):
                        cache_creation_input_tokens = chunk.message.usage.cache_creation_input_tokens
                    if hasattr(chunk.message.usage, "cache_read_input_tokens"):
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
                # Check for updated cache metrics
                if hasattr(chunk.usage, "cache_creation_input_tokens"):
                    cache_creation_input_tokens = chunk.usage.cache_creation_input_tokens
                if hasattr(chunk.usage, "cache_read_input_tokens"):
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
                
                # UPDATED: Token accounting for billing with cache adjustments
                adjusted_prompt_tokens = input_tokens

                # Cache write premium: add full cache tokens plus 25% premium
                if cache_creation_input_tokens > 0:
                    cache_write_premium = int(cache_creation_input_tokens * 0.25)
                    adjusted_prompt_tokens += cache_creation_input_tokens + cache_write_premium

                # Cache read discount: only charge 10% of cached tokens (90% discount)
                if cache_read_input_tokens > 0:
                    adjusted_prompt_tokens += int(cache_read_input_tokens * 0.1)
                
                # Get usage with adjusted token count for billing
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
    ) -> tuple[str, list[dict]]:
        """
        Convert prompt messages to dict list and system
        """
        system = ""
        system_components = []
        first_loop = True
        for message in prompt_messages:
            if isinstance(message, SystemPromptMessage):
                if isinstance(message.content, str):
                    content = message.content.strip()
                    if "<cache>" in content:
                        system_components.append({
                            "type": "text",
                            "text": content.replace("<cache>", ""),
                            "cache_control": {"type": "ephemeral"}
                        })
                    else:
                        system_components.append({"type": "text", "text": content})
                    
                    if first_loop:
                        system = content
                        first_loop = False
                    else:
                        system += "\n"
                        system += content
                elif isinstance(message.content, list):
                    combined_content = ""
                    for c in message.content:
                        if isinstance(c, TextPromptMessageContent):
                            text_content = c.data.strip()
                            combined_content += text_content
                    
                    if "<cache>" in combined_content:
                        system_components.append({
                            "type": "text",
                            "text": combined_content.replace("<cache>", ""),
                            "cache_control": {"type": "ephemeral"}
                        })
                    else:
                        system_components.append({"type": "text", "text": combined_content})
                    
                    if first_loop:
                        system = combined_content
                        first_loop = False
                    else:
                        system += "\n"
                        system += combined_content
                else:
                    raise ValueError(
                        f"Unknown system prompt message content type {type(message.content)}"
                    )
        
        # If we have structured system components with cache controls, use them instead of a single string
        if len(system_components) > 0 and any(comp.get("cache_control") for comp in system_components):
            system = system_components
        
        prompt_message_dicts = []
        for message in prompt_messages:
            if not isinstance(message, SystemPromptMessage):
                if isinstance(message, UserPromptMessage):
                    message = cast(UserPromptMessage, message)
                    if isinstance(message.content, str):
                        if "<cache>" in message.content:
                            message_dict = {
                                "role": "user", 
                                "content": [{
                                    "type": "text",
                                    "text": message.content.replace("<cache>", ""),
                                    "cache_control": {"type": "ephemeral"}
                                }]
                            }
                        else:
                            message_dict = {"role": "user", "content": message.content}
                        prompt_message_dicts.append(message_dict)
                    else:
                        sub_messages = []
                        for message_content in message.content or []:
                            if message_content.type == PromptMessageContentType.TEXT:
                                message_content = cast(
                                    TextPromptMessageContent, message_content
                                )
                                text_content = message_content.data
                                if "<cache>" in text_content:
                                    sub_message_dict = {
                                        "type": "text",
                                        "text": text_content.replace("<cache>", ""),
                                        "cache_control": {"type": "ephemeral"}
                                    }
                                else:
                                    sub_message_dict = {
                                        "type": "text",
                                        "text": text_content,
                                    }
                                sub_messages.append(sub_message_dict)
                            elif message_content.type == PromptMessageContentType.IMAGE:
                                message_content = cast(
                                    ImagePromptMessageContent, message_content
                                )
                                if not message_content.data.startswith("data:"):
                                    try:
                                        image_content = requests.get(
                                            message_content.data
                                        ).content
                                        with Image.open(
                                            io.BytesIO(image_content)
                                        ) as img:
                                            mime_type = f"image/{img.format.lower()}"
                                        base64_data = base64.b64encode(
                                            image_content
                                        ).decode("utf-8")
                                    except Exception as ex:
                                        raise ValueError(
                                            f"Failed to fetch image data from url {message_content.data}, {ex}"
                                        )
                                else:
                                    data_split = message_content.data.split(";base64,")
                                    mime_type = data_split[0].replace("data:", "")
                                    base64_data = data_split[1]
                                if mime_type not in {
                                    "image/jpeg",
                                    "image/png",
                                    "image/gif",
                                    "image/webp",
                                }:
                                    raise ValueError(
                                        f"Unsupported image type {mime_type}, only support image/jpeg, image/png, image/gif, and image/webp"
                                    )
                                sub_message_dict = {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime_type,
                                        "data": base64_data,
                                    },
                                }
                                sub_messages.append(sub_message_dict)
                            elif isinstance(
                                message_content, DocumentPromptMessageContent
                            ):
                                if message_content.mime_type != "application/pdf":
                                    raise ValueError(
                                        f"Unsupported document type {message_content.mime_type}, only support application/pdf"
                                    )
                                sub_message_dict = {
                                    "type": "document",
                                    "source": {
                                        "type": "base64",
                                        "media_type": message_content.mime_type,
                                        "data": message_content.base64_data,
                                    },
                                }
                                sub_messages.append(sub_message_dict)
                        prompt_message_dicts.append(
                            {"role": "user", "content": sub_messages}
                        )
                elif isinstance(message, AssistantPromptMessage):
                    message = cast(AssistantPromptMessage, message)
                    content = []
                    
                    if self.previous_thinking_blocks and any(isinstance(msg, ToolPromptMessage) for msg in prompt_messages):
                        content.extend(self.previous_thinking_blocks)
                    
                    if self.previous_redacted_thinking_blocks and any(isinstance(msg, ToolPromptMessage) for msg in prompt_messages):
                        content.extend(self.previous_redacted_thinking_blocks)
                    
                    if message.tool_calls:
                        for tool_call in message.tool_calls:
                            content.append({
                                "type": "tool_use",
                                "id": tool_call.id,
                                "name": tool_call.function.name,
                                "input": json.loads(tool_call.function.arguments),
                            })
                    elif message.content:
                        if "<cache>" in message.content:
                            content.append({
                                "type": "text", 
                                "text": message.content.replace("<cache>", ""),
                                "cache_control": {"type": "ephemeral"}
                            })
                        else:
                            content.append({"type": "text", "text": message.content})
                    if prompt_message_dicts and prompt_message_dicts[-1]["role"] == "assistant":
                        prompt_message_dicts[-1]["content"].extend(content)
                    else:
                        prompt_message_dicts.append(
                            {"role": "assistant", "content": content}
                        )
                elif isinstance(message, ToolPromptMessage):
                    message = cast(ToolPromptMessage, message)
                    content = message.content
                    if "<cache>" in content:
                        message_dict = {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": message.tool_call_id,
                                    "content": content.replace("<cache>", ""),
                                    "cache_control": {"type": "ephemeral"}
                                }
                            ],
                        }
                    else:
                        message_dict = {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": message.tool_call_id,
                                    "content": content,
                                }
                            ],
                        }
                    prompt_message_dicts.append(message_dict)
                else:
                    raise ValueError(f"Got unknown type {message}")
                    
        return (system, prompt_message_dicts)

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
            if not isinstance(message.content, list):
                message_text = f"{ai_prompt} {content}"
            else:
                message_text = ""
                for sub_message in message.content:
                    if sub_message.type == PromptMessageContentType.TEXT:
                        message_text += f"{ai_prompt} {sub_message.data}"
                    elif sub_message.type == PromptMessageContentType.IMAGE:
                        message_text += f"{ai_prompt} [IMAGE]"
        elif isinstance(message, SystemPromptMessage):
            message_text = content
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
