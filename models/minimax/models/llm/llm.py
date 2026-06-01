import json
from collections.abc import Generator, Sequence
from typing import Any, Mapping, Optional, Union

import anthropic
from anthropic import Anthropic, Stream
from anthropic.types import Message
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    PromptMessage,
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


class MinimaxLargeLanguageModel(LargeLanguageModel):
    _OPAQUE_ANTHROPIC_CONTENT_KEY = "minimax_anthropic_content"
    _MODEL_ALIASES = {
        "minimax-m3": "MiniMax-M3",
        "minimax-m2.7": "MiniMax-M2.7",
        "minimax-m2.7-highspeed": "MiniMax-M2.7-highspeed",
        "minimax-m2.7lightning": "MiniMax-M2.7-highspeed",
        "minimax-m2.7-lightning": "MiniMax-M2.7-highspeed",
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
        thinking_payload = self._normalize_thinking_payload(
            thinking=thinking,
            thinking_budget=thinking_budget,
            request_model=request_model,
        )
        if thinking_payload:
            request_kwargs["thinking"] = thinking_payload

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

    def _convert_user_content_blocks(self, content: Any) -> list[dict[str, Any]]:
        if not isinstance(content, list):
            return [{"type": "text", "text": self._extract_text_content(content)}]

        content_blocks: list[dict[str, Any]] = []
        for item in content:
            block = self._convert_user_content_block(item)
            if block is not None:
                content_blocks.append(block)

        if not content_blocks:
            return [{"type": "text", "text": ""}]
        return content_blocks

    def _convert_user_content_block(self, content: Any) -> Optional[dict[str, Any]]:
        if isinstance(content, TextPromptMessageContent):
            return {"type": "text", "text": content.data}
        if isinstance(content, ImagePromptMessageContent):
            return self._create_media_content_block("image", content.data)
        if isinstance(content, VideoPromptMessageContent):
            return self._create_media_content_block("video", content.data)

        if isinstance(content, dict):
            content_type = content.get("type")
            if self._is_content_type(content_type, "text"):
                return {
                    "type": "text",
                    "text": str(content.get("data") or content.get("text") or ""),
                }
            if self._is_content_type(content_type, "image", "image_url"):
                image_url = self._extract_media_url(content, "image_url")
                return self._create_media_content_block("image", str(image_url or ""))
            if self._is_content_type(content_type, "video", "video_url"):
                video_url = self._extract_media_url(content, "video_url")
                return self._create_media_content_block("video", str(video_url or ""))
            return None

        content_type = getattr(content, "type", None)
        if self._is_content_type(content_type, "text"):
            return {"type": "text", "text": str(getattr(content, "data", ""))}
        if self._is_content_type(content_type, "image"):
            return self._create_media_content_block("image", str(getattr(content, "data", "")))
        if self._is_content_type(content_type, "video"):
            return self._create_media_content_block("video", str(getattr(content, "data", "")))
        return None

    def _is_content_type(self, content_type: Any, *expected: str) -> bool:
        content_type_value = getattr(content_type, "value", content_type)
        return content_type_value in expected

    def _extract_media_url(self, content: dict[str, Any], media_key: str) -> Any:
        media_url = content.get("data") or content.get("url")
        if media_url:
            return media_url

        media_value = content.get(media_key)
        if isinstance(media_value, dict):
            return media_value.get("url")
        if isinstance(media_value, str):
            return media_value
        return None

    def _create_media_content_block(self, block_type: str, data: str) -> Optional[dict[str, Any]]:
        data = data.strip()
        if not data:
            return None
        return {"type": block_type, "source": self._create_media_source(data)}

    def _create_media_source(self, data: str) -> dict[str, Any]:
        if data.startswith("data:") and ";base64," in data:
            header, encoded = data.split(";base64,", 1)
            return {
                "type": "base64",
                "media_type": header.removeprefix("data:"),
                "data": encoded,
            }
        return {"type": "url", "url": data}

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

    def _parse_tool_arguments(self, arguments: str) -> dict[str, Any]:
        try:
            input_payload = json.loads(arguments or "{}")
        except Exception:
            return {"raw": arguments}
        if not isinstance(input_payload, dict):
            return {"value": input_payload}
        return input_payload

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
        tools: Optional[list[PromptMessageTool]] = None,
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
                            name=getattr(block, "name", ""),
                            arguments=json.dumps(input_payload),
                        ),
                    )
                )

        if tool_calls and thinking_blocks:
            self._set_previous_thinking_blocks(thinking_blocks)
        else:
            self._set_previous_thinking_blocks([])

        # 构建包含思考内容的完整文本
        assistant_text = ""
        if thinking_blocks:
            # 将所有思考内容用<think>标签包裹
            thinking_contents = []
            for block in thinking_blocks:
                if block.get("type") == "thinking":
                    thinking_contents.append(block.get("thinking", ""))
                elif block.get("type") == "redacted_thinking":
                    thinking_contents.append("[Redacted thinking]")

            if thinking_contents:
                assistant_text = "<think>" + "".join(thinking_contents) + "</think>\n"

        # 添加正常文本内容
        assistant_text += "".join(text_chunks)

        opaque_body = None
        if response_content_blocks:
            opaque_body = {self._OPAQUE_ANTHROPIC_CONTENT_KEY: response_content_blocks}

        assistant_message = AssistantPromptMessage(
            content=assistant_text,
            tool_calls=tool_calls,
            opaque_body=opaque_body,
        )

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
        streamed_tool_input_buffers: dict[str, str] = {}
        streamed_tool_input_fallbacks: dict[str, str] = {}
        streamed_content_blocks: dict[str, dict[str, Any]] = {}
        streamed_thinking_blocks: dict[str, dict[str, Any]] = {}
        current_thinking_blocks: list[dict[str, Any]] = []
        emitted_final = False
        is_reasoning_started = 0  # 0 not started, 1 started, 2 ended

        def close_reasoning_chunk(index: int = 0) -> Optional[LLMResultChunk]:
            nonlocal is_reasoning_started
            if is_reasoning_started != 1:
                return None
            is_reasoning_started = 2
            return LLMResultChunk(
                model=model,
                prompt_messages=prompt_messages,
                delta=LLMResultChunkDelta(
                    index=index,
                    message=AssistantPromptMessage(content="\n</think>\n"),
                ),
            )

        def finalize_tool_calls() -> list[AssistantPromptMessage.ToolCall]:
            final_tool_calls: list[AssistantPromptMessage.ToolCall] = []
            for index in sorted(
                streamed_tool_calls,
                key=lambda value: (0, int(value)) if value.isdigit() else (1, value),
            ):
                tool_call = streamed_tool_calls[index]
                arguments = (
                    streamed_tool_input_buffers.get(index)
                    or streamed_tool_input_fallbacks.get(index)
                    or "{}"
                )
                tool_call.function.arguments = arguments
                content_block = streamed_content_blocks.get(index)
                if content_block is not None and content_block.get("type") == "tool_use":
                    content_block["input"] = self._parse_tool_arguments(arguments)
                final_tool_calls.append(tool_call)
            return final_tool_calls

        def build_opaque_body() -> Optional[dict[str, Any]]:
            if not streamed_content_blocks:
                return None
            content_blocks = [
                streamed_content_blocks[index]
                for index in sorted(
                    streamed_content_blocks,
                    key=lambda value: (0, int(value)) if value.isdigit() else (1, value),
                )
            ]
            return {self._OPAQUE_ANTHROPIC_CONTENT_KEY: content_blocks}

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
                            name=getattr(block, "name", ""),
                            arguments="",
                        ),
                    )
                elif getattr(block, "type", "") == "thinking":
                    # 开始思考块时,输出<think>标签
                    if is_reasoning_started == 0:
                        yield LLMResultChunk(
                            model=model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=0,
                                message=AssistantPromptMessage(content="<think>\n"),
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
                    current_thinking_blocks.append(thinking_block)
                elif getattr(block, "type", "") == "redacted_thinking":
                    thinking_block = {"type": "redacted_thinking"}
                    streamed_content_blocks[index] = thinking_block
                    current_thinking_blocks.append(thinking_block)
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
                            str(event_index),
                            {"type": "text", "text": ""},
                        )
                        if content_block.get("type") == "text":
                            content_block["text"] = str(content_block.get("text", "")) + text
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
                        index = str(event_index)
                        thinking_block = streamed_thinking_blocks.get(index)
                        if thinking_block is None:
                            thinking_block = {
                                "type": "thinking",
                                "thinking": "",
                                "signature": "",
                            }
                            streamed_content_blocks[index] = thinking_block
                            streamed_thinking_blocks[index] = thinking_block
                            current_thinking_blocks.append(thinking_block)
                        prev = str(thinking_block.get("thinking", ""))
                        thinking_block["thinking"] = prev + thinking
                        # 实时输出思考内容
                        if is_reasoning_started == 0:
                            yield LLMResultChunk(
                                model=model,
                                prompt_messages=prompt_messages,
                                delta=LLMResultChunkDelta(
                                    index=event_index,
                                    message=AssistantPromptMessage(content="<think>\n"),
                                ),
                            )
                            is_reasoning_started = 1
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
                        thinking_block["signature"] = signature
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
                                    name="",
                                    arguments="",
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
                    output_tokens = int(getattr(usage, "output_tokens", output_tokens) or output_tokens)
                continue

            if event_type == "message_stop":
                closing_chunk = close_reasoning_chunk(0)
                if closing_chunk is not None:
                    yield closing_chunk
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

                final_tool_calls = finalize_tool_calls()

                if final_tool_calls and current_thinking_blocks:
                    self._set_previous_thinking_blocks(current_thinking_blocks)
                else:
                    self._set_previous_thinking_blocks([])

                yield LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(
                            content="",
                            tool_calls=final_tool_calls,
                            opaque_body=build_opaque_body(),
                        ),
                        usage=usage,
                        finish_reason=finish_reason or "stop",
                    ),
                )
                emitted_final = True

        if not emitted_final:
            closing_chunk = close_reasoning_chunk(0)
            if closing_chunk is not None:
                yield closing_chunk
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

            final_tool_calls = finalize_tool_calls()

            if final_tool_calls and current_thinking_blocks:
                self._set_previous_thinking_blocks(current_thinking_blocks)
            else:
                self._set_previous_thinking_blocks([])

            yield LLMResultChunk(
                model=model,
                prompt_messages=prompt_messages,
                delta=LLMResultChunkDelta(
                    index=0,
                    message=AssistantPromptMessage(
                        content="",
                        tool_calls=final_tool_calls,
                        opaque_body=build_opaque_body(),
                    ),
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

    def _normalize_thinking_payload(
        self,
        *,
        thinking: Any,
        thinking_budget: int,
        request_model: str,
    ) -> Optional[dict[str, Any]]:
        if isinstance(thinking, dict):
            return thinking

        if isinstance(thinking, str):
            thinking_type = thinking.strip().lower()
            if thinking_type in {"adaptive", "disabled"}:
                return {"type": thinking_type}
            if thinking_type in {"enabled", "true"}:
                if request_model == "MiniMax-M3":
                    return {"type": "adaptive"}
                return {"type": "enabled", "budget_tokens": max(1024, thinking_budget)}
            if thinking_type in {"false", "none", "off"}:
                if request_model == "MiniMax-M3":
                    return {"type": "disabled"}
                return None

        if thinking is True:
            if request_model == "MiniMax-M3":
                return {"type": "adaptive"}
            return {"type": "enabled", "budget_tokens": max(1024, thinking_budget)}
        if thinking is False and request_model == "MiniMax-M3":
            return {"type": "disabled"}
        return None

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
