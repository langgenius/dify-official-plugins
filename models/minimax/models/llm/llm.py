import json
from collections.abc import Generator, Sequence
from typing import Any, Mapping, Optional, Union

import anthropic
from anthropic import Anthropic, Stream
from anthropic.types import Message
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
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


class MinimaxLargeLanguageModel(LargeLanguageModel):
    _MODEL_ALIASES = {
        "minimax-m2.5": "MiniMax-M2.5",
        "minimax-m2.5lightning": "MiniMax-M2.5-highspeed",
        "minimax-m2.5-lightning": "MiniMax-M2.5-highspeed",
        "minimax-m2.1": "MiniMax-M2.1",
        "minimax-m2.1-lightning": "MiniMax-M2.1-highspeed",
        "minimax-m2": "MiniMax-M2",
        "minimax-m2-her": "MiniMax-M2",
        "minimax-m1": "MiniMax-M2.5",
    }

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
        credentials: dict[str, Any],
        prompt_messages: Sequence[PromptMessage],
        model_parameters: dict[str, Any],
        tools: Optional[list[PromptMessageTool]] = None,
        stop: Optional[Sequence[str]] = None,
        stream: bool = True,
        user: Optional[str] = None,
    ) -> Union[LLMResult, Generator]:
        request_model = self._resolve_model_name(model)
        credentials_kwargs = self._to_credential_kwargs(credentials)
        client = Anthropic(**credentials_kwargs)

        model_parameters = dict(model_parameters)
        if "max_tokens_to_sample" in model_parameters and "max_tokens" not in model_parameters:
            model_parameters["max_tokens"] = model_parameters.pop("max_tokens_to_sample")
        if "max_output_tokens" in model_parameters and "max_tokens" not in model_parameters:
            model_parameters["max_tokens"] = model_parameters.pop("max_output_tokens")

        thinking = model_parameters.pop("thinking", None)
        thinking_budget = int(model_parameters.pop("thinking_budget", 1024) or 1024)

        max_tokens = int(model_parameters.pop("max_tokens", 1024) or 1024)
        if max_tokens <= 0:
            max_tokens = 1024

        system, prompt_message_dicts = self._convert_prompt_messages(prompt_messages)

        request_kwargs: dict[str, Any] = {
            "model": request_model,
            "messages": prompt_message_dicts,
            "max_tokens": max_tokens,
        }

        if system:
            request_kwargs["system"] = system
        if stop:
            request_kwargs["stop_sequences"] = list(stop)
        if user:
            request_kwargs["metadata"] = {"user_id": user}
        if thinking is True:
            request_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": max(1024, thinking_budget),
            }
        elif isinstance(thinking, dict):
            request_kwargs["thinking"] = thinking

        for key in ("temperature", "top_p", "top_k"):
            if key in model_parameters and model_parameters[key] is not None:
                request_kwargs[key] = model_parameters[key]

        if tools:
            request_kwargs["tools"] = self._transform_tool_prompt(tools)

        if stream:
            response = client.messages.create(stream=True, **request_kwargs)
            return self._handle_chat_generate_stream_response(
                model=model,
                prompt_messages=list(prompt_messages),
                credentials=credentials,
                response=response,
                tools=tools,
            )

        response = client.messages.create(stream=False, **request_kwargs)
        return self._handle_chat_generate_response(
            model=model,
            prompt_messages=list(prompt_messages),
            credentials=credentials,
            response=response,
            tools=tools,
        )

    def validate_credentials(self, model: str, credentials: Mapping[str, Any]) -> None:
        request_model = self._resolve_model_name(model)
        credentials_kwargs = self._to_credential_kwargs(credentials)
        client = Anthropic(**credentials_kwargs)

        try:
            client.messages.create(
                model=request_model,
                max_tokens=8,
                messages=[{"role": "user", "content": "ping"}],
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as ex:
            raise CredentialsValidateFailedError(str(ex))
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> int:
        prompt = "\n".join(self._extract_text_content(message.content) for message in prompt_messages)
        return self._get_num_tokens_by_gpt2(prompt)

    def _convert_prompt_messages(
        self,
        prompt_messages: Sequence[PromptMessage],
    ) -> tuple[str, list[dict[str, Any]]]:
        system_parts: list[str] = []
        message_dicts: list[dict[str, Any]] = []

        if not any(isinstance(message, ToolPromptMessage) for message in prompt_messages):
            self._set_previous_thinking_blocks([])

        for message in prompt_messages:
            if isinstance(message, SystemPromptMessage):
                content = self._extract_text_content(message.content)
                if content:
                    system_parts.append(content)
                continue

            converted = self._convert_prompt_message_to_anthropic_message(message)
            if converted is not None:
                message_dicts.append(converted)

        if not message_dicts:
            message_dicts = [{"role": "user", "content": [{"type": "text", "text": " "}]}]

        return "\n".join(system_parts), self._merge_consecutive_messages(message_dicts)

    def _convert_prompt_message_to_anthropic_message(
        self, prompt_message: PromptMessage
    ) -> Optional[dict[str, Any]]:
        if isinstance(prompt_message, UserPromptMessage):
            text = self._extract_text_content(prompt_message.content)
            return {"role": "user", "content": [{"type": "text", "text": text}]}

        if isinstance(prompt_message, AssistantPromptMessage):
            content_blocks: list[dict[str, Any]] = []

            previous_thinking_blocks = self._get_previous_thinking_blocks()
            if prompt_message.tool_calls and previous_thinking_blocks:
                content_blocks.extend(previous_thinking_blocks)

            text = self._extract_text_content(prompt_message.content)
            if text:
                content_blocks.append({"type": "text", "text": text})

            if prompt_message.tool_calls:
                for tool_call in prompt_message.tool_calls:
                    arguments = tool_call.function.arguments or "{}"
                    try:
                        input_payload = json.loads(arguments)
                    except Exception:
                        input_payload = {"raw": arguments}
                    if not isinstance(input_payload, dict):
                        input_payload = {"value": input_payload}
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tool_call.id,
                            "name": tool_call.function.name,
                            "input": input_payload,
                        }
                    )

            if not content_blocks:
                content_blocks.append({"type": "text", "text": ""})

            return {"role": "assistant", "content": content_blocks}

        if isinstance(prompt_message, ToolPromptMessage):
            text = self._extract_text_content(prompt_message.content)
            tool_call_id = prompt_message.tool_call_id or ""
            return {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tool_call_id, "content": text}],
            }

        return None

    def _merge_consecutive_messages(
        self, message_dicts: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        for message in message_dicts:
            role = message.get("role")
            content = self._normalize_content_blocks(message.get("content"))
            if not merged or merged[-1].get("role") != role:
                merged.append({"role": role, "content": content})
            else:
                merged[-1]["content"].extend(content)
        return merged

    def _normalize_content_blocks(self, content: Any) -> list[dict[str, Any]]:
        if isinstance(content, str):
            return [{"type": "text", "text": content}]
        if isinstance(content, list):
            normalized: list[dict[str, Any]] = []
            for item in content:
                if isinstance(item, dict):
                    normalized.append(item)
            return normalized
        return []

    def _extract_text_content(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, TextPromptMessageContent):
                    text_parts.append(item.data)
                elif isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(str(item.get("data") or item.get("text") or ""))
                elif hasattr(item, "type") and getattr(item, "type", None) == "text":
                    if hasattr(item, "data"):
                        text_parts.append(str(item.data))
                    elif hasattr(item, "text"):
                        text_parts.append(str(item.text))
            return " ".join(part for part in text_parts if part)
        return str(content)

    def _transform_tool_prompt(self, tools: list[PromptMessageTool]) -> list[dict[str, Any]]:
        transformed_tools: list[dict[str, Any]] = []
        for tool in tools:
            input_schema: Any = tool.parameters
            if isinstance(input_schema, str):
                try:
                    input_schema = json.loads(input_schema)
                except Exception:
                    input_schema = {}
            if not isinstance(input_schema, dict):
                input_schema = {}

            transformed_tools.append(
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": input_schema,
                }
            )
        return transformed_tools

    def _handle_chat_generate_response(
        self,
        model: str,
        prompt_messages: list[PromptMessage],
        credentials: dict,
        response: Message,
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> LLMResult:
        text_chunks: list[str] = []
        tool_calls: list[AssistantPromptMessage.ToolCall] = []
        thinking_blocks: list[dict[str, Any]] = []

        for block in response.content:
            block_type = getattr(block, "type", "")
            if block_type == "text":
                text = getattr(block, "text", "")
                if text:
                    text_chunks.append(text)
            elif block_type == "thinking":
                thinking_text = getattr(block, "thinking", "")
                if thinking_text:
                    thinking_blocks.append(
                        {
                            "type": "thinking",
                            "thinking": thinking_text,
                            "signature": getattr(block, "signature", ""),
                        }
                    )
            elif block_type == "redacted_thinking":
                thinking_blocks.append({"type": "redacted_thinking"})
            elif block_type == "tool_use":
                input_payload = getattr(block, "input", {}) or {}
                if not isinstance(input_payload, dict):
                    input_payload = {"value": input_payload}
                tool_calls.append(
                    AssistantPromptMessage.ToolCall(
                        id=getattr(block, "id", ""),
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=getattr(block, "name", ""),
                            arguments=json.dumps(input_payload),
                        ),
                    )
                )

        if tool_calls and thinking_blocks:
            self._set_previous_thinking_blocks(thinking_blocks)
        else:
            self._set_previous_thinking_blocks([])

        assistant_text = "".join(text_chunks)
        assistant_message = AssistantPromptMessage(content=assistant_text, tool_calls=tool_calls)

        prompt_tokens = int(getattr(response.usage, "input_tokens", 0) or 0)
        completion_tokens = int(getattr(response.usage, "output_tokens", 0) or 0)
        if prompt_tokens == 0:
            prompt_tokens = self.get_num_tokens(
                model=model,
                credentials=credentials,
                prompt_messages=prompt_messages,
                tools=tools,
            )
        if completion_tokens == 0:
            completion_tokens = self.get_num_tokens(
                model=model,
                credentials=credentials,
                prompt_messages=[assistant_message],
                tools=None,
            )

        usage = self._calc_response_usage(
            model=model,
            credentials=credentials,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        return LLMResult(
            model=model,
            prompt_messages=prompt_messages,
            message=assistant_message,
            usage=usage,
        )

    def _handle_chat_generate_stream_response(
        self,
        model: str,
        prompt_messages: list[PromptMessage],
        credentials: dict,
        response: Stream,
        tools: Optional[list[PromptMessageTool]] = None,
    ) -> Generator[LLMResultChunk, None, None]:
        input_tokens = 0
        output_tokens = 0
        finish_reason: Optional[str] = None
        streamed_text: list[str] = []
        streamed_tool_calls: dict[str, AssistantPromptMessage.ToolCall] = {}
        current_thinking_blocks: list[dict[str, Any]] = []
        emitted_final = False

        for event in response:
            event_type = getattr(event, "type", "")

            if event_type == "message_start":
                usage = getattr(getattr(event, "message", None), "usage", None)
                if usage is not None:
                    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
                continue

            if event_type == "content_block_start":
                block = getattr(event, "content_block", None)
                if getattr(block, "type", "") == "tool_use":
                    index = str(getattr(event, "index", len(streamed_tool_calls)))
                    input_payload = getattr(block, "input", {}) or {}
                    if not isinstance(input_payload, dict):
                        input_payload = {"value": input_payload}
                    streamed_tool_calls[index] = AssistantPromptMessage.ToolCall(
                        id=getattr(block, "id", index),
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=getattr(block, "name", ""),
                            arguments=json.dumps(input_payload),
                        ),
                    )
                elif getattr(block, "type", "") == "thinking":
                    current_thinking_blocks.append(
                        {
                            "type": "thinking",
                            "thinking": "",
                            "signature": getattr(block, "signature", ""),
                        }
                    )
                elif getattr(block, "type", "") == "redacted_thinking":
                    current_thinking_blocks.append({"type": "redacted_thinking"})
                continue

            if event_type == "content_block_delta":
                delta = getattr(event, "delta", None)
                delta_type = getattr(delta, "type", "")
                event_index = int(getattr(event, "index", 0) or 0)

                if delta_type == "text_delta":
                    text = getattr(delta, "text", "")
                    if text:
                        streamed_text.append(text)
                        yield LLMResultChunk(
                            model=model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=event_index,
                                message=AssistantPromptMessage(content=text),
                            ),
                        )
                elif delta_type == "thinking_delta":
                    thinking = getattr(delta, "thinking", "")
                    if thinking:
                        if not current_thinking_blocks or current_thinking_blocks[-1].get("type") != "thinking":
                            current_thinking_blocks.append(
                                {
                                    "type": "thinking",
                                    "thinking": "",
                                    "signature": "",
                                }
                            )
                        prev = str(current_thinking_blocks[-1].get("thinking", ""))
                        current_thinking_blocks[-1]["thinking"] = prev + thinking
                elif delta_type == "signature_delta":
                    signature = getattr(delta, "signature", "")
                    if signature and current_thinking_blocks and current_thinking_blocks[-1].get("type") == "thinking":
                        current_thinking_blocks[-1]["signature"] = signature
                elif delta_type == "input_json_delta":
                    partial_json = getattr(delta, "partial_json", "")
                    if partial_json:
                        index = str(event_index)
                        if index not in streamed_tool_calls:
                            streamed_tool_calls[index] = AssistantPromptMessage.ToolCall(
                                id=f"tool_{index}",
                                type="function",
                                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                    name="",
                                    arguments="",
                                ),
                            )
                        streamed_tool_calls[index].function.arguments += partial_json
                continue

            if event_type == "message_delta":
                delta = getattr(event, "delta", None)
                finish_reason = self._convert_finish_reason(getattr(delta, "stop_reason", None))
                usage = getattr(event, "usage", None)
                if usage is not None:
                    output_tokens = int(getattr(usage, "output_tokens", output_tokens) or output_tokens)
                continue

            if event_type == "message_stop":
                assistant_text = "".join(streamed_text)
                if input_tokens == 0:
                    input_tokens = self.get_num_tokens(
                        model=model,
                        credentials=credentials,
                        prompt_messages=prompt_messages,
                        tools=tools,
                    )
                if output_tokens == 0:
                    output_tokens = self._get_num_tokens_by_gpt2(assistant_text)

                usage = self._calc_response_usage(
                    model=model,
                    credentials=credentials,
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens,
                )

                final_tool_calls = list(streamed_tool_calls.values())
                for tool_call in final_tool_calls:
                    if not tool_call.function.arguments:
                        tool_call.function.arguments = "{}"

                if final_tool_calls and current_thinking_blocks:
                    self._set_previous_thinking_blocks(current_thinking_blocks)
                else:
                    self._set_previous_thinking_blocks([])

                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(content="", tool_calls=final_tool_calls),
                        usage=usage,
                        finish_reason=finish_reason or "stop",
                    ),
                )
                emitted_final = True

        if not emitted_final:
            assistant_text = "".join(streamed_text)
            if input_tokens == 0:
                input_tokens = self.get_num_tokens(
                    model=model,
                    credentials=credentials,
                    prompt_messages=prompt_messages,
                    tools=tools,
                )
            if output_tokens == 0:
                output_tokens = self._get_num_tokens_by_gpt2(assistant_text)

            usage = self._calc_response_usage(
                model=model,
                credentials=credentials,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
            )

            final_tool_calls = list(streamed_tool_calls.values())
            for tool_call in final_tool_calls:
                if not tool_call.function.arguments:
                    tool_call.function.arguments = "{}"

            if final_tool_calls and current_thinking_blocks:
                self._set_previous_thinking_blocks(current_thinking_blocks)
            else:
                self._set_previous_thinking_blocks([])

            yield LLMResultChunk(
                model=model,
                prompt_messages=prompt_messages,
                delta=LLMResultChunkDelta(
                    index=0,
                    message=AssistantPromptMessage(content="", tool_calls=final_tool_calls),
                    usage=usage,
                    finish_reason=finish_reason or "stop",
                ),
            )

    def _get_previous_thinking_blocks(self) -> list[dict[str, Any]]:
        raw_blocks = getattr(self, "_previous_thinking_blocks", None)
        if not isinstance(raw_blocks, list):
            return []
        thinking_blocks: list[dict[str, Any]] = []
        for item in raw_blocks:
            if isinstance(item, dict):
                thinking_blocks.append(item)
        return thinking_blocks

    def _set_previous_thinking_blocks(self, thinking_blocks: list[dict[str, Any]]) -> None:
        setattr(self, "_previous_thinking_blocks", thinking_blocks)

    def _to_credential_kwargs(self, credentials: Mapping[str, Any]) -> dict[str, Any]:
        api_key = str(credentials.get("minimax_api_key") or "").strip()
        if not api_key:
            raise CredentialsValidateFailedError("Invalid API key")

        endpoint_url = str(credentials.get("endpoint_url") or "https://api.minimax.io").strip()
        if not endpoint_url.startswith("http://") and not endpoint_url.startswith("https://"):
            endpoint_url = f"https://{endpoint_url}"
        endpoint_url = endpoint_url.rstrip("/")
        if not endpoint_url.endswith("/anthropic"):
            endpoint_url = f"{endpoint_url}/anthropic"

        return {
            "api_key": api_key,
            "base_url": endpoint_url,
            "default_headers": {
                "Authorization": f"Bearer {api_key}",
            },
        }

    def _resolve_model_name(self, model: str) -> str:
        if model in self._MODEL_ALIASES:
            return self._MODEL_ALIASES[model]
        model_lower = model.lower()
        if model_lower in self._MODEL_ALIASES:
            return self._MODEL_ALIASES[model_lower]
        return model

    def _convert_finish_reason(self, finish_reason: Optional[str]) -> Optional[str]:
        if finish_reason is None:
            return None
        mapping = {
            "end_turn": "stop",
            "stop_sequence": "stop",
            "max_tokens": "length",
            "tool_use": "tool_calls",
        }
        return mapping.get(finish_reason, finish_reason)

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {
            InvokeConnectionError: [anthropic.APIConnectionError],
            InvokeServerUnavailableError: [anthropic.InternalServerError],
            InvokeRateLimitError: [anthropic.RateLimitError],
            InvokeAuthorizationError: [anthropic.AuthenticationError, anthropic.PermissionDeniedError],
            InvokeBadRequestError: [
                anthropic.BadRequestError,
                anthropic.NotFoundError,
                anthropic.UnprocessableEntityError,
                KeyError,
                ValueError,
            ],
        }
