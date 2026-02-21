import logging
from collections.abc import Generator
from collections.abc import Mapping
from typing import Any, cast

from volcenginesdkarkruntime import Ark
from volcenginesdkarkruntime._streaming import Stream
from volcenginesdkarkruntime.types.chat import ChatCompletion, ChatCompletionChunk

from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    AudioPromptMessageContent,
    DocumentPromptMessageContent,
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
    VideoPromptMessageContent,
)
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeError
from dify_plugin.interfaces.model.large_language_model import LargeLanguageModel

logger = logging.getLogger(__name__)


def _convert_prompt_message_tool_to_dict(tool: PromptMessageTool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _convert_content_to_ark(content: Any) -> Any:
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    parts: list[dict[str, Any]] = []
    for message_content in content:
        if message_content.type == PromptMessageContentType.TEXT:
            message_content = cast(TextPromptMessageContent, message_content)
            parts.append({"type": "text", "text": message_content.data})
        elif message_content.type == PromptMessageContentType.IMAGE:
            message_content = cast(ImagePromptMessageContent, message_content)
            detail = "high" if message_content.detail == ImagePromptMessageContent.DETAIL.HIGH else "low"
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": message_content.data,
                        "detail": detail,
                    },
                }
            )
        elif message_content.type == PromptMessageContentType.VIDEO:
            message_content = cast(VideoPromptMessageContent, message_content)
            parts.append({"type": "video_url", "video_url": {"url": message_content.data}})
        elif message_content.type == PromptMessageContentType.AUDIO:
            message_content = cast(AudioPromptMessageContent, message_content)
            parts.append({"type": "text", "text": message_content.data})
        elif message_content.type == PromptMessageContentType.DOCUMENT:
            message_content = cast(DocumentPromptMessageContent, message_content)
            parts.append({"type": "text", "text": message_content.data})
        else:
            parts.append({"type": "text", "text": str(message_content)})

    return parts


def _convert_prompt_message_to_dict(message: PromptMessage) -> dict[str, Any]:
    if isinstance(message, SystemPromptMessage):
        return {"role": "system", "content": _convert_content_to_ark(message.content) or ""}

    if isinstance(message, UserPromptMessage):
        return {"role": "user", "content": _convert_content_to_ark(message.content) or ""}

    if isinstance(message, AssistantPromptMessage):
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": _convert_content_to_ark(message.content) or "",
        }

        if message.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": call.id,
                    "type": call.type or "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in message.tool_calls
            ]

        return msg

    if isinstance(message, ToolPromptMessage):
        return {
            "role": "tool",
            "content": _convert_content_to_ark(message.content) or "",
            "tool_call_id": message.tool_call_id,
        }

    role = getattr(getattr(message, "role", None), "value", None) or "user"
    return {"role": role, "content": _convert_content_to_ark(getattr(message, "content", "")) or ""}


def _wrap_thinking(content: str, reasoning_content: str | None, is_reasoning: bool) -> tuple[str, bool]:
    content = content or ""

    if reasoning_content:
        if not is_reasoning:
            return "<think>\n" + reasoning_content, True
        return reasoning_content, True

    if is_reasoning:
        return "\n</think>" + (content or ""), False

    return content, False


class VolcengineArkLargeLanguageModel(LargeLanguageModel):
    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {}

    def validate_credentials(self, model: str, credentials: Mapping[str, Any]) -> None:
        try:
            client = Ark(
                base_url=credentials["api_endpoint_host"],
                api_key=credentials["ark_api_key"],
            )
            # minimal non-stream call
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=8,
            )
        except Exception as e:
            raise CredentialsValidateFailedError(e)

    def get_num_tokens(
        self,
        model: str,
        credentials: dict[str, Any],
        prompt_messages: list[PromptMessage],
        tools: list[PromptMessageTool] | None = None,
    ) -> int:
        # No official token counter exposed here; fall back to rough estimate.
        # This is acceptable for plugin implementations that do not support token counting.
        text = "".join(getattr(m, "content", "") if isinstance(getattr(m, "content", ""), str) else "" for m in prompt_messages)
        return max(1, len(text) // 4)

    def _invoke(
        self,
        model: str,
        credentials: dict[str, Any],
        prompt_messages: list[PromptMessage],
        model_parameters: dict[str, Any],
        tools: list[PromptMessageTool] | None = None,
        stop: list[str] | None = None,
        stream: bool = True,
        user: str | None = None,
    ) -> LLMResult | Generator[LLMResultChunk, None, None]:
        client = Ark(
            base_url=credentials["api_endpoint_host"],
            api_key=credentials["ark_api_key"],
        )

        messages = [_convert_prompt_message_to_dict(m) for m in prompt_messages]

        params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": model_parameters.get("temperature"),
            "top_p": model_parameters.get("top_p"),
            "max_tokens": model_parameters.get("max_tokens"),
            "stop": stop,
            "user": user,
        }

        if tools:
            params["tools"] = [_convert_prompt_message_tool_to_dict(t) for t in tools]

            if "tool_choice" in model_parameters:
                params["tool_choice"] = model_parameters.get("tool_choice")
            if "parallel_tool_calls" in model_parameters:
                params["parallel_tool_calls"] = model_parameters.get("parallel_tool_calls")

        def _handle_stream() -> Generator[LLMResultChunk, None, None]:
            try:
                stream_options = model_parameters.get("stream_options")
                if stream_options is None:
                    stream_options = {"include_usage": True}

                req = {k: v for k, v in params.items() if v is not None}
                req["stream_options"] = stream_options

                resp = cast(
                    Stream[ChatCompletionChunk],
                    client.chat.completions.create(**req, stream=True),
                )

                aggregated_tool_calls: dict[int, AssistantPromptMessage.ToolCall] = {}
                usage_obj = None
                is_reasoning_started = False

                chunk_index = 0

                final_chunk = LLMResultChunk(
                    model=model,
                    prompt_messages=prompt_messages,
                    delta=LLMResultChunkDelta(
                        index=0,
                        message=AssistantPromptMessage(content=""),
                    ),
                )

                for chunk in resp:
                    if len(chunk.choices) == 0:
                        if chunk.usage:
                            usage_obj = chunk.usage
                        continue

                    choice = chunk.choices[0]
                    delta = choice.delta

                    delta_content = delta.content or ""
                    delta_reasoning = delta.reasoning_content
                    processed_content, is_reasoning_started = _wrap_thinking(
                        delta_content, delta_reasoning, is_reasoning_started
                    )

                    if delta.tool_calls:
                        for tool_call_chunk in delta.tool_calls:
                            idx = tool_call_chunk.index
                            existing = aggregated_tool_calls.get(idx)
                            if existing is None:
                                fn_name = ""
                                fn_args = ""
                                if tool_call_chunk.function:
                                    fn_name = tool_call_chunk.function.name or ""
                                    fn_args = tool_call_chunk.function.arguments or ""
                                aggregated_tool_calls[idx] = AssistantPromptMessage.ToolCall(
                                    id=tool_call_chunk.id or "",
                                    type=tool_call_chunk.type or "function",
                                    function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                        name=fn_name,
                                        arguments=fn_args,
                                    ),
                                )
                            else:
                                if tool_call_chunk.id:
                                    existing.id = tool_call_chunk.id
                                if tool_call_chunk.type:
                                    existing.type = tool_call_chunk.type
                                if tool_call_chunk.function:
                                    if tool_call_chunk.function.name:
                                        existing.function.name = tool_call_chunk.function.name
                                    if tool_call_chunk.function.arguments:
                                        existing.function.arguments += tool_call_chunk.function.arguments

                    if choice.finish_reason == "tool_calls" and aggregated_tool_calls:
                        tool_calls = [
                            aggregated_tool_calls[i]
                            for i in sorted(aggregated_tool_calls)
                            if aggregated_tool_calls[i] is not None
                        ]
                        yield LLMResultChunk(
                            model=chunk.model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=chunk_index,
                                message=AssistantPromptMessage(content="", tool_calls=tool_calls),
                                finish_reason="tool_calls",
                            ),
                        )
                        chunk_index += 1
                        continue

                    if processed_content:
                        yield LLMResultChunk(
                            model=chunk.model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=chunk_index,
                                message=AssistantPromptMessage(content=processed_content),
                            ),
                        )
                        chunk_index += 1

                    if choice.finish_reason is not None and choice.finish_reason != "tool_calls":
                        final_chunk = LLMResultChunk(
                            model=chunk.model,
                            prompt_messages=prompt_messages,
                            delta=LLMResultChunkDelta(
                                index=chunk_index,
                                message=AssistantPromptMessage(content=""),
                                finish_reason=choice.finish_reason,
                            ),
                        )

                if usage_obj is not None:
                    try:
                        usage = self._calc_response_usage(
                            model=model,
                            credentials=credentials,
                            prompt_tokens=usage_obj.prompt_tokens,
                            completion_tokens=usage_obj.completion_tokens,
                        )
                        final_chunk.delta.usage = usage
                    except Exception:
                        pass

                yield final_chunk
            except Exception as e:
                raise InvokeError(str(e))

        def _handle_block() -> LLMResult:
            try:
                resp = cast(
                    ChatCompletion,
                    client.chat.completions.create(
                        **{k: v for k, v in params.items() if v is not None},
                        stream=False,
                    ),
                )
                choice = resp.choices[0]
                msg = choice.message

                tool_calls = []
                if msg.tool_calls:
                    for call in msg.tool_calls:
                        tool_calls.append(
                            AssistantPromptMessage.ToolCall(
                                id=call.id,
                                type=call.type,
                                function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                                    name=call.function.name,
                                    arguments=call.function.arguments,
                                ),
                            )
                        )

                content = msg.content or ""
                reasoning_content = msg.reasoning_content
                if reasoning_content:
                    content = f"<think>\n{reasoning_content}\n</think>\n" + (content or "")

                usage_obj = resp.usage
                if usage_obj is None:
                    prompt_tokens = self.get_num_tokens(model, credentials, prompt_messages, tools)
                    completion_tokens = max(1, len(content) // 4)
                else:
                    prompt_tokens = usage_obj.prompt_tokens
                    completion_tokens = usage_obj.completion_tokens

                usage = self._calc_response_usage(
                    model=model,
                    credentials=credentials,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )

                return LLMResult(
                    model=model,
                    prompt_messages=prompt_messages,
                    message=AssistantPromptMessage(content=content, tool_calls=tool_calls),
                    usage=usage,
                )
            except Exception as e:
                raise InvokeError(str(e))

        return _handle_stream() if stream else _handle_block()
