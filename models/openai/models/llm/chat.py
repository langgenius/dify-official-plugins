from __future__ import annotations

import json
from collections.abc import Generator, Iterable
from typing import TYPE_CHECKING, Any, cast

from openai import OpenAI
from openai.types.chat import ChatCompletion

from dify_plugin.entities.model.llm import (
    LLMResult,
    LLMResultChunk,
    LLMResultChunkDelta,
)
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    AudioPromptMessageContent,
    DeveloperPromptMessage,
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
from dify_plugin.errors.model import InvokeBadRequestError, InvokeConnectionError

from ..common_openai import _user_digest
from . import tokens

if TYPE_CHECKING:
    from .llm import OpenAILargeLanguageModel

THINKING_PREFIXES = ("o", "gpt-5")


def generate_chat(
    llm: OpenAILargeLanguageModel,
    client: OpenAI,
    model: str,
    credentials: dict,
    prompt_messages: list[PromptMessage],
    model_parameters: dict,
    tools: list[PromptMessageTool] | None,
    stop: list[str] | None,
    stream: bool,
    user: str | None,
) -> LLMResult | Generator[LLMResultChunk, None, None]:
    params = _chat_params(model_parameters)
    if uses_max_completion_tokens(model) and "max_tokens" in params:
        params["max_completion_tokens"] = params.pop("max_tokens")
    if tools:
        params["tools"] = [_tool(tool) for tool in tools]
        params.setdefault("tool_choice", "auto")
    if stop:
        params["stop"] = stop
    _add_identity(params, user, credentials)
    if stream:
        params["stream_options"] = {"include_usage": True}

    response = client.chat.completions.create(
        model=model,
        messages=cast(Any, [message(item) for item in prompt_messages]),
        stream=stream,
        **params,
    )
    if stream:
        return _chat_stream(
            llm,
            cast(Iterable[Any], response),
            model,
            credentials,
            prompt_messages,
            tools,
        )
    return _chat_result(
        llm,
        cast(ChatCompletion, response),
        model,
        credentials,
        prompt_messages,
        tools,
    )


def message(prompt: PromptMessage) -> dict[str, Any]:
    if isinstance(prompt, UserPromptMessage):
        content: Any = (
            prompt.content
            if isinstance(prompt.content, str)
            else [_user_content(item) for item in prompt.content or []]
        )
        result = {"role": "user", "content": content}
    elif isinstance(prompt, AssistantPromptMessage):
        result = {"role": "assistant", "content": _assistant_content(prompt)}
        if prompt.tool_calls:
            result["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in prompt.tool_calls
            ]
    elif isinstance(prompt, (SystemPromptMessage, DeveloperPromptMessage)):
        result = {"role": prompt.role.value, "content": _text_content(prompt)}
    elif isinstance(prompt, ToolPromptMessage):
        result = {
            "role": "tool",
            "content": _text_content(prompt),
            "tool_call_id": prompt.tool_call_id,
        }
    else:
        raise InvokeBadRequestError(
            f"Unsupported Chat Completions message: {type(prompt).__name__}"
        )

    if prompt.name and result["role"] != "tool":
        result["name"] = prompt.name
    return result


def _chat_params(model_parameters: dict) -> dict:
    params = model_parameters.copy()
    unsupported = [
        name
        for name in ("reasoning_summary", "reasoning_mode", "reasoning_context")
        if params.pop(name, None) not in (None, "")
    ]
    if unsupported:
        raise InvokeBadRequestError(
            f"{', '.join(unsupported)} requires the Responses API"
        )

    response_format = params.pop("response_format", None)
    schema = params.pop("json_schema", None)
    if isinstance(response_format, dict):
        params["response_format"] = response_format
    elif response_format:
        format_type = str(response_format).lower()
        if format_type == "json_schema":
            params["response_format"] = {
                "type": "json_schema",
                "json_schema": _json_schema(schema),
            }
        else:
            params["response_format"] = {"type": format_type}
    return params


def uses_max_completion_tokens(model: str) -> bool:
    base_model = model.split(":", 2)[1] if model.startswith("ft:") else model
    return base_model.startswith(THINKING_PREFIXES)


def _add_identity(params: dict, user: str | None, credentials: dict) -> None:
    if not user:
        return
    digest = _user_digest(user)
    if credentials.get("openai_api_base"):
        params["user"] = digest
    else:
        params.setdefault("safety_identifier", digest)
        params.setdefault("prompt_cache_key", digest)


def _json_schema(value: Any) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise InvokeBadRequestError("JSON Schema must be valid JSON") from error
    if not isinstance(value, dict):
        raise InvokeBadRequestError("JSON Schema must be an object")
    if "schema" not in value:
        return {"name": "response", "schema": value}
    result = value.copy()
    result.setdefault("name", "response")
    return result


def _user_content(content: Any) -> dict:
    if isinstance(content, TextPromptMessageContent):
        return {"type": "text", "text": content.data}
    if isinstance(content, ImagePromptMessageContent):
        if not content.url and not content.base64_data:
            raise InvokeBadRequestError("Image input must include data")
        return {
            "type": "image_url",
            "image_url": {"url": content.data, "detail": content.detail.value},
        }
    if isinstance(content, AudioPromptMessageContent):
        data = content.base64_data
        if not data and content.data.startswith("data:"):
            data = content.data.partition(",")[2]
        if not data:
            raise InvokeBadRequestError("Audio input must include base64 data")
        audio_format = content.format.lstrip(".")
        if audio_format not in ("mp3", "wav"):
            raise InvokeBadRequestError("Audio input must be MP3 or WAV")
        return {
            "type": "input_audio",
            "input_audio": {
                "data": data,
                "format": audio_format,
            },
        }
    if isinstance(content, DocumentPromptMessageContent):
        raise InvokeBadRequestError("Document input requires the Responses API")
    raise InvokeBadRequestError(
        f"Unsupported Chat Completions content type: {content.type.value}"
    )


def _assistant_content(prompt: AssistantPromptMessage) -> str | None:
    if isinstance(prompt.content, str) or prompt.content is None:
        return prompt.content
    return _text_content(prompt)


def _text_content(prompt: PromptMessage) -> str:
    if isinstance(prompt.content, str):
        return prompt.content
    content = prompt.content or []
    if any(item.type != PromptMessageContentType.TEXT for item in content):
        raise InvokeBadRequestError(
            f"{prompt.role.value} messages only support text content"
        )
    return "".join(cast(TextPromptMessageContent, item).data for item in content)


def _tool(tool: PromptMessageTool) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _chat_result(
    llm: OpenAILargeLanguageModel,
    response: ChatCompletion,
    model: str,
    credentials: dict,
    prompt_messages: list[PromptMessage],
    tools: list[PromptMessageTool] | None,
) -> LLMResult:
    choice = response.choices[0]
    reply = choice.message
    content = (reply.content or "") + (reply.refusal or "")
    raw_calls = _calls(reply.tool_calls or [])
    if not raw_calls and reply.function_call:
        function = reply.function_call
        raw_calls = [
            _call(function.name or "", function.name or "", function.arguments or "")
        ]
    calls = raw_calls if choice.finish_reason in ("tool_calls", "function_call") else []
    message = AssistantPromptMessage(content=content, tool_calls=calls)
    if response.usage:
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
    else:
        prompt_tokens = tokens.count_messages(model, prompt_messages, tools)
        completion_tokens = tokens.count_messages(
            model,
            [AssistantPromptMessage(content=content, tool_calls=raw_calls)],
        )
    return LLMResult(
        model=response.model,
        message=message,
        usage=llm._calc_response_usage(
            model, credentials, prompt_tokens, completion_tokens
        ),
        system_fingerprint=response.system_fingerprint,
    )


def _chat_stream(
    llm: OpenAILargeLanguageModel,
    response: Iterable[Any],
    model: str,
    credentials: dict,
    prompt_messages: list[PromptMessage],
    tools: list[PromptMessageTool] | None,
) -> Generator[LLMResultChunk, None, None]:
    text = ""
    usage = None
    finish_reason = None
    response_model = model
    fingerprint = None
    fragments: dict[int, dict[str, str]] = {}
    try:
        for chunk in response:
            response_model = chunk.model or response_model
            fingerprint = chunk.system_fingerprint or fingerprint
            if chunk.usage:
                usage = chunk.usage
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            piece = (delta.content or "") + (delta.refusal or "")
            if piece:
                text += piece
                yield _chunk(response_model, piece, choice.index, fingerprint)
            for part in delta.tool_calls or []:
                fragment = fragments.setdefault(
                    part.index,
                    {"id": "", "name": "", "arguments": ""},
                )
                fragment["id"] = part.id or fragment["id"]
                if part.function:
                    fragment["name"] = part.function.name or fragment["name"]
                    fragment["arguments"] += part.function.arguments or ""
            if delta.function_call:
                fragment = fragments.setdefault(
                    -1, {"id": "", "name": "", "arguments": ""}
                )
                fragment["name"] = delta.function_call.name or fragment["name"]
                fragment["id"] = fragment["name"]
                fragment["arguments"] += delta.function_call.arguments or ""
            if choice.finish_reason:
                finish_reason = choice.finish_reason
    finally:
        _close(response)

    if finish_reason is None:
        raise InvokeConnectionError(
            "OpenAI Chat Completions stream ended without a finish reason"
        )

    calls = (
        [
            _call(item["id"], item["name"], item["arguments"])
            for _, item in sorted(fragments.items())
        ]
        if finish_reason in ("tool_calls", "function_call")
        else []
    )
    if usage:
        prompt_tokens = usage.prompt_tokens
        completion_tokens = usage.completion_tokens
    else:
        prompt_tokens = tokens.count_messages(model, prompt_messages, tools)
        completion_tokens = tokens.count_text(
            model,
            text + "".join(item["arguments"] for _, item in sorted(fragments.items())),
        )
    result_usage = llm._calc_response_usage(
        model,
        credentials,
        prompt_tokens,
        completion_tokens,
    )
    yield LLMResultChunk(
        model=response_model,
        system_fingerprint=fingerprint,
        delta=LLMResultChunkDelta(
            index=0,
            message=AssistantPromptMessage(content="", tool_calls=calls),
            finish_reason="tool_calls" if calls else finish_reason,
            usage=result_usage,
        ),
    )


def _calls(items: Iterable[Any]) -> list[AssistantPromptMessage.ToolCall]:
    return [
        _call(item.id or "", item.function.name or "", item.function.arguments or "")
        for item in items
    ]


def _call(call_id: str, name: str, arguments: str) -> AssistantPromptMessage.ToolCall:
    return AssistantPromptMessage.ToolCall(
        id=call_id,
        type="function",
        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
            name=name,
            arguments=arguments,
        ),
    )


def _chunk(
    model: str, content: str, index: int, fingerprint: str | None
) -> LLMResultChunk:
    return LLMResultChunk(
        model=model,
        system_fingerprint=fingerprint,
        delta=LLMResultChunkDelta(
            index=index,
            message=AssistantPromptMessage(content=content),
        ),
    )


def _close(stream: Any) -> None:
    close = getattr(stream, "close", None)
    if callable(close):
        close()
