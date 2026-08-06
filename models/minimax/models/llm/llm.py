import json
from collections.abc import Generator, Mapping, Sequence
from typing import Any

import anthropic
from anthropic import Anthropic, Stream
from anthropic.types import Message
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
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

from models.llm._functional import (
    convert_finish_reason,
    generation_options,
    index_sort_key,
    merge_consecutive_messages,
    normalize_anthropic_endpoint,
    normalize_thinking_payload,
    parse_json_object,
    render_assistant_text,
    resolve_model_name,
    text_content,
    user_content_block,
)


class MinimaxLargeLanguageModel(LargeLanguageModel):
    _OPAQUE_ANTHROPIC_CONTENT_KEY = "minimax_anthropic_content"

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
        tools: list[PromptMessageTool] | None = None,
        stop: Sequence[str] | None = None,
        stream: bool = True,
        user: str | None = None,
    ) -> LLMResult | Generator:
        request_model = self._resolve_model_name(model)
        credentials_kwargs = self._to_credential_kwargs(credentials)
        client = Anthropic(**credentials_kwargs)
        options = generation_options(model_parameters, request_model)

        system, prompt_message_dicts = self._convert_prompt_messages(prompt_messages)

        request_kwargs: dict[str, Any] = {
            "model": request_model,
            "messages": prompt_message_dicts,
            "max_tokens": options.max_tokens,
        }

        if system:
            request_kwargs["system"] = system
        if stop:
            request_kwargs["stop_sequences"] = list(stop)
        if user:
            request_kwargs["metadata"] = {"user_id": user}
        thinking_payload = self._normalize_thinking_payload(
            thinking=options.thinking,
            thinking_budget=options.thinking_budget,
            request_model=request_model,
        )
        if thinking_payload:
            request_kwargs["thinking"] = thinking_payload

        request_kwargs.update(options.sampling)

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
                exclude_reasoning_tokens=options.exclude_reasoning_tokens,
            )

        response = client.messages.create(stream=False, **request_kwargs)
        return self._handle_chat_generate_response(
            model=model,
            prompt_messages=list(prompt_messages),
            credentials=credentials,
            response=response,
            tools=tools,
            exclude_reasoning_tokens=options.exclude_reasoning_tokens,
        )

    def validate_credentials(self, model: str, credentials: Mapping[str, Any]) -> None:
        request_model = self._resolve_model_name(model)
        credentials_kwargs = self._to_credential_kwargs(credentials)
        client = Anthropic(**credentials_kwargs)

        try:
            client.messages.create(
                model=request_model, max_tokens=8, messages=[{"role": "user", "content": "ping"}]
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

    def get_num_tokens(
        self,
        model: str,
        credentials: dict,
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> int:
        prompt = "\n".join(
            self._extract_text_content(message.content) for message in prompt_messages
        )
        return self._get_num_tokens_by_gpt2(prompt)

    def _convert_prompt_messages(
        self, prompt_messages: Sequence[PromptMessage]
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
    ) -> dict[str, Any] | None:
        if isinstance(prompt_message, UserPromptMessage):
            return {
                "role": "user",
                "content": self._convert_user_content_blocks(prompt_message.content),
            }

        if isinstance(prompt_message, AssistantPromptMessage):
            opaque_content_blocks = self._get_opaque_anthropic_content(prompt_message)
            if prompt_message.tool_calls and opaque_content_blocks:
                return {"role": "assistant", "content": opaque_content_blocks}

            content_blocks: list[dict[str, Any]] = []

            previous_thinking_blocks = self._get_previous_thinking_blocks()
            if prompt_message.tool_calls and previous_thinking_blocks:
                content_blocks.extend(previous_thinking_blocks)

            text = self._extract_text_content(prompt_message.content)
            if prompt_message.tool_calls and previous_thinking_blocks:
                text = self._strip_leading_thinking_text(text)
            if text:
                content_blocks.append({"type": "text", "text": text})

            if prompt_message.tool_calls:
                for tool_call in prompt_message.tool_calls:
                    arguments = tool_call.function.arguments or "{}"
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tool_call.id,
                            "name": tool_call.function.name,
                            "input": self._parse_tool_arguments(arguments),
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

    def _convert_user_content_blocks(self, content: Any) -> list[dict[str, Any]]:
        if not isinstance(content, list):
            return [{"type": "text", "text": self._extract_text_content(content)}]

        content_blocks = [
            block
            for item in content
            if (block := self._convert_user_content_block(item)) is not None
        ]
        return content_blocks or [{"type": "text", "text": ""}]

    def _convert_user_content_block(self, content: Any) -> dict[str, Any] | None:
        return user_content_block(content)

    def _merge_consecutive_messages(
        self, message_dicts: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return merge_consecutive_messages(message_dicts)

    def _extract_text_content(self, content: Any) -> str:
        return text_content(content)

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

    def _parse_tool_arguments(self, arguments: str) -> dict[str, Any]:
        return parse_json_object(arguments)

    def _get_opaque_anthropic_content(
        self, prompt_message: AssistantPromptMessage
    ) -> list[dict[str, Any]]:
        opaque_body = prompt_message.opaque_body
        if not isinstance(opaque_body, dict):
            return []
        raw_content = opaque_body.get(self._OPAQUE_ANTHROPIC_CONTENT_KEY)
        if not isinstance(raw_content, list):
            return []

        content_blocks: list[dict[str, Any]] = []
        for block in raw_content:
            if isinstance(block, dict):
                content_blocks.append(block)
        return content_blocks

    def _strip_leading_thinking_text(self, text: str) -> str:
        if not text.startswith("<think>"):
            return text
        end_tag = "</think>"
        end_index = text.find(end_tag)
        if end_index < 0:
            return text
        return text[end_index + len(end_tag) :].lstrip("\n")

    def _handle_chat_generate_response(
        self,
        model: str,
        prompt_messages: list[PromptMessage],
        credentials: dict,
        response: Message,
        tools: list[PromptMessageTool] | None = None,
        exclude_reasoning_tokens: bool = False,
    ) -> LLMResult:
        text_chunks: list[str] = []
        tool_calls: list[AssistantPromptMessage.ToolCall] = []
        thinking_blocks: list[dict[str, Any]] = []
        response_content_blocks: list[dict[str, Any]] = []

        for block in response.content:
            block_type = getattr(block, "type", "")
            if block_type == "text":
                text = getattr(block, "text", "")
                if text:
                    text_chunks.append(text)
                    response_content_blocks.append({"type": "text", "text": text})
            elif block_type == "thinking":
                thinking_text = getattr(block, "thinking", "")
                if thinking_text:
                    thinking_block = {
                        "type": "thinking",
                        "thinking": thinking_text,
                        "signature": getattr(block, "signature", ""),
                    }
                    thinking_blocks.append(thinking_block)
                    response_content_blocks.append(thinking_block)
            elif block_type == "redacted_thinking":
                thinking_block = {"type": "redacted_thinking"}
                thinking_blocks.append(thinking_block)
                response_content_blocks.append(thinking_block)
            elif block_type == "tool_use":
                input_payload = getattr(block, "input", {}) or {}
                if not isinstance(input_payload, dict):
                    input_payload = {"value": input_payload}
                response_content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": getattr(block, "id", ""),
                        "name": getattr(block, "name", ""),
                        "input": input_payload,
                    }
                )
                tool_calls.append(
                    AssistantPromptMessage.ToolCall(
                        id=getattr(block, "id", ""),
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=getattr(block, "name", ""), arguments=json.dumps(input_payload)
                        ),
                    )
                )

        if tool_calls and thinking_blocks:
            self._set_previous_thinking_blocks(thinking_blocks)
        else:
            self._set_previous_thinking_blocks([])

        assistant_text = render_assistant_text(
            thinking_blocks, text_chunks, hide_thinking=exclude_reasoning_tokens
        )

        opaque_body = None
        if response_content_blocks:
            opaque_body = {self._OPAQUE_ANTHROPIC_CONTENT_KEY: response_content_blocks}

        assistant_message = AssistantPromptMessage(
            content=assistant_text, tool_calls=tool_calls, opaque_body=opaque_body
        )

        prompt_tokens = int(getattr(response.usage, "input_tokens", 0) or 0)
        completion_tokens = int(getattr(response.usage, "output_tokens", 0) or 0)
        if prompt_tokens == 0:
            prompt_tokens = self.get_num_tokens(
                model=model, credentials=credentials, prompt_messages=prompt_messages, tools=tools
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
            model=model, prompt_messages=prompt_messages, message=assistant_message, usage=usage
        )

    def _handle_chat_generate_stream_response(
        self,
        model: str,
        prompt_messages: list[PromptMessage],
        credentials: dict,
        response: Stream,
        tools: list[PromptMessageTool] | None = None,
        exclude_reasoning_tokens: bool = False,
    ) -> Generator[LLMResultChunk, None, None]:
        input_tokens = 0
        output_tokens = 0
        finish_reason: str | None = None
        streamed_text: list[str] = []
        streamed_tool_calls: dict[str, AssistantPromptMessage.ToolCall] = {}
        streamed_tool_input_buffers: dict[str, str] = {}
        streamed_tool_input_fallbacks: dict[str, str] = {}
        streamed_content_blocks: dict[str, dict[str, Any]] = {}
        streamed_thinking_blocks: dict[str, dict[str, Any]] = {}
        is_reasoning_started = 0  # 0 not started, 1 started, 2 ended

        def close_reasoning_chunk(index: int = 0) -> LLMResultChunk | None:
            nonlocal is_reasoning_started
            if is_reasoning_started != 1:
                return None
            is_reasoning_started = 2
            if exclude_reasoning_tokens:
                return None
            return LLMResultChunk(
                model=model,
                prompt_messages=prompt_messages,
                delta=LLMResultChunkDelta(
                    index=index, message=AssistantPromptMessage(content="\n</think>\n")
                ),
            )

        def tool_arguments(index: str) -> str:
            return (
                streamed_tool_input_buffers.get(index)
                or streamed_tool_input_fallbacks.get(index)
                or "{}"
            )

        def finalize_tool_call(index: str) -> AssistantPromptMessage.ToolCall:
            seed = streamed_tool_calls[index]
            return AssistantPromptMessage.ToolCall(
                id=seed.id,
                type="function",
                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                    name=seed.function.name, arguments=tool_arguments(index)
                ),
            )

        def finalize_tool_calls() -> list[AssistantPromptMessage.ToolCall]:
            return [
                finalize_tool_call(index)
                for index in sorted(streamed_tool_calls, key=index_sort_key)
            ]

        def finalized_content_block(index: str) -> dict[str, Any]:
            block = streamed_content_blocks[index]
            if block.get("type") != "tool_use":
                return block
            return {**block, "input": self._parse_tool_arguments(tool_arguments(index))}

        def ordered_content_blocks() -> list[dict[str, Any]]:
            return [
                finalized_content_block(index)
                for index in sorted(streamed_content_blocks, key=index_sort_key)
            ]

        def thinking_content_blocks() -> list[dict[str, Any]]:
            return [
                block
                for block in ordered_content_blocks()
                if block.get("type") in {"thinking", "redacted_thinking"}
            ]

        def build_opaque_body() -> dict[str, Any] | None:
            if not streamed_content_blocks:
                return None
            return {self._OPAQUE_ANTHROPIC_CONTENT_KEY: ordered_content_blocks()}

        for event in response:
            event_type = getattr(event, "type", "")

            if event_type == "message_start":
                usage = getattr(getattr(event, "message", None), "usage", None)
                if usage is not None:
                    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
                continue

            if event_type == "content_block_start":
                block = getattr(event, "content_block", None)
                index = str(getattr(event, "index", len(streamed_content_blocks)))
                if getattr(block, "type", "") == "tool_use":
                    closing_chunk = close_reasoning_chunk(int(index) if index.isdigit() else 0)
                    if closing_chunk is not None:
                        yield closing_chunk
                    input_payload = getattr(block, "input", {}) or {}
                    if not isinstance(input_payload, dict):
                        input_payload = {"value": input_payload}
                    streamed_tool_input_fallbacks[index] = json.dumps(input_payload)
                    streamed_content_blocks[index] = {
                        "type": "tool_use",
                        "id": getattr(block, "id", index),
                        "name": getattr(block, "name", ""),
                        "input": input_payload,
                    }
                    streamed_tool_calls[index] = AssistantPromptMessage.ToolCall(
                        id=getattr(block, "id", index),
                        type="function",
                        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                            name=getattr(block, "name", ""), arguments=""
                        ),
                    )
                elif getattr(block, "type", "") == "thinking":
                    # 开始思考块时,输出<think>标签
                    if is_reasoning_started == 0 and not exclude_reasoning_tokens:
                        yield LLMResultChunk(
                            model=model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=0, message=AssistantPromptMessage(content="<think>\n")
                            ),
                        )
                        is_reasoning_started = 1
                    thinking_block = {
                        "type": "thinking",
                        "thinking": "",
                        "signature": getattr(block, "signature", ""),
                    }
                    streamed_content_blocks[index] = thinking_block
                    streamed_thinking_blocks[index] = thinking_block
                elif getattr(block, "type", "") == "redacted_thinking":
                    thinking_block = {"type": "redacted_thinking"}
                    streamed_content_blocks[index] = thinking_block
                elif getattr(block, "type", "") == "text":
                    streamed_content_blocks[index] = {
                        "type": "text",
                        "text": getattr(block, "text", "") or "",
                    }
                continue

            if event_type == "content_block_delta":
                delta = getattr(event, "delta", None)
                delta_type = getattr(delta, "type", "")
                event_index = int(getattr(event, "index", 0) or 0)

                if delta_type == "text_delta":
                    text = getattr(delta, "text", "")
                    if text:
                        # 如果之前在思考状态,先结束思考标签
                        closing_chunk = close_reasoning_chunk(event_index)
                        if closing_chunk is not None:
                            yield closing_chunk
                        streamed_text.append(text)
                        content_block = streamed_content_blocks.setdefault(
                            str(event_index), {"type": "text", "text": ""}
                        )
                        if content_block.get("type") == "text":
                            streamed_content_blocks[str(event_index)] = {
                                **content_block,
                                "text": str(content_block.get("text", "")) + text,
                            }
                        yield LLMResultChunk(
                            model=model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=event_index, message=AssistantPromptMessage(content=text)
                            ),
                        )
                elif delta_type == "thinking_delta":
                    thinking = getattr(delta, "thinking", "")
                    if thinking:
                        index = str(event_index)
                        thinking_block = streamed_thinking_blocks.get(index)
                        if thinking_block is None:
                            thinking_block = {"type": "thinking", "thinking": "", "signature": ""}
                            streamed_content_blocks[index] = thinking_block
                            streamed_thinking_blocks[index] = thinking_block
                        thinking_block = {
                            **thinking_block,
                            "thinking": str(thinking_block.get("thinking", "")) + thinking,
                        }
                        streamed_content_blocks[index] = thinking_block
                        streamed_thinking_blocks[index] = thinking_block
                        # 实时输出思考内容
                        if is_reasoning_started == 0 and not exclude_reasoning_tokens:
                            yield LLMResultChunk(
                                model=model,
                                prompt_messages=prompt_messages,
                                delta=LLMResultChunkDelta(
                                    index=event_index,
                                    message=AssistantPromptMessage(content="<think>\n"),
                                ),
                            )
                            is_reasoning_started = 1
                        if not exclude_reasoning_tokens:
                            yield LLMResultChunk(
                                model=model,
                                prompt_messages=prompt_messages,
                                delta=LLMResultChunkDelta(
                                    index=event_index,
                                    message=AssistantPromptMessage(content=thinking),
                                ),
                            )
                elif delta_type == "signature_delta":
                    signature = getattr(delta, "signature", "")
                    thinking_block = streamed_thinking_blocks.get(str(event_index))
                    if signature and thinking_block is not None:
                        thinking_block = {**thinking_block, "signature": signature}
                        streamed_content_blocks[str(event_index)] = thinking_block
                        streamed_thinking_blocks[str(event_index)] = thinking_block
                elif delta_type == "input_json_delta":
                    partial_json = getattr(delta, "partial_json", "")
                    if partial_json:
                        index = str(event_index)
                        if index not in streamed_tool_calls:
                            streamed_tool_input_fallbacks[index] = "{}"
                            streamed_content_blocks[index] = {
                                "type": "tool_use",
                                "id": f"tool_{index}",
                                "name": "",
                                "input": {},
                            }
                            streamed_tool_calls[index] = AssistantPromptMessage.ToolCall(
                                id=f"tool_{index}",
                                type="function",
                                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                    name="", arguments=""
                                ),
                            )
                        streamed_tool_input_buffers[index] = (
                            streamed_tool_input_buffers.get(index, "") + partial_json
                        )
                continue

            if event_type == "message_delta":
                delta = getattr(event, "delta", None)
                finish_reason = self._convert_finish_reason(getattr(delta, "stop_reason", None))
                usage = getattr(event, "usage", None)
                if usage is not None:
                    output_tokens = int(
                        getattr(usage, "output_tokens", output_tokens) or output_tokens
                    )
                continue

            if event_type == "message_stop":
                closing_chunk = close_reasoning_chunk(0)
                if closing_chunk is not None:
                    yield closing_chunk
                break

        closing_chunk = close_reasoning_chunk(0)
        if closing_chunk is not None:
            yield closing_chunk

        assistant_text = "".join(streamed_text)
        if input_tokens == 0:
            input_tokens = self.get_num_tokens(
                model=model, credentials=credentials, prompt_messages=prompt_messages, tools=tools
            )
        if output_tokens == 0:
            output_tokens = self._get_num_tokens_by_gpt2(assistant_text)

        usage = self._calc_response_usage(
            model=model,
            credentials=credentials,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        )
        final_tool_calls = finalize_tool_calls()
        current_thinking_blocks = thinking_content_blocks()
        self._set_previous_thinking_blocks(current_thinking_blocks if final_tool_calls else [])

        yield LLMResultChunk(
            model=model,
            prompt_messages=prompt_messages,
            delta=LLMResultChunkDelta(
                index=0,
                message=AssistantPromptMessage(
                    content="", tool_calls=final_tool_calls, opaque_body=build_opaque_body()
                ),
                usage=usage,
                finish_reason=finish_reason or "stop",
            ),
        )

    def _get_previous_thinking_blocks(self) -> list[dict[str, Any]]:
        raw_blocks = getattr(self, "_previous_thinking_blocks", None)
        return (
            [item for item in raw_blocks if isinstance(item, dict)]
            if isinstance(raw_blocks, list)
            else []
        )

    def _set_previous_thinking_blocks(self, thinking_blocks: list[dict[str, Any]]) -> None:
        self._previous_thinking_blocks = list(thinking_blocks)

    def _normalize_thinking_payload(
        self, *, thinking: Any, thinking_budget: int, request_model: str
    ) -> dict[str, Any] | None:
        return normalize_thinking_payload(
            thinking=thinking, thinking_budget=thinking_budget, request_model=request_model
        )

    def _to_credential_kwargs(self, credentials: Mapping[str, Any]) -> dict[str, Any]:
        api_key = str(credentials.get("minimax_api_key") or "").strip()
        if not api_key:
            raise CredentialsValidateFailedError("Invalid API key")

        endpoint_url = normalize_anthropic_endpoint(credentials.get("endpoint_url"))

        return {
            "api_key": api_key,
            "base_url": endpoint_url,
            "default_headers": {"Authorization": f"Bearer {api_key}"},
        }

    def _resolve_model_name(self, model: str) -> str:
        return resolve_model_name(model)

    def _convert_finish_reason(self, finish_reason: str | None) -> str | None:
        return convert_finish_reason(finish_reason)

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {
            InvokeConnectionError: [anthropic.APIConnectionError],
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
                KeyError,
                ValueError,
            ],
        }
