from __future__ import annotations

import copy
import hashlib
import json
import logging
from collections.abc import Generator, Iterable
from typing import Any, Mapping, Optional, Sequence, cast

from openai import OpenAI
from httpx import Timeout
from dify_plugin.entities.model.llm import LLMResult, LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
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
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

logger = logging.getLogger(__name__)

OUTPUT_KEY = "responses_output"
APP_CODE_HEADER = {"APP-Code": "Dify2025"}


# ---------------------------------------------------------------------------
# Helpers ported from openai/models/llm/responses.py
# ---------------------------------------------------------------------------

def _user_digest(user: str) -> str:
    return hashlib.sha256(user.encode()).hexdigest()


def _supports_encrypted_reasoning(model: str) -> bool:
    base_model = model.split(":", 2)[1] if model.startswith("ft:") else model
    return (
        base_model.startswith("gpt-5") and not base_model.endswith("-chat-latest")
    ) or (len(base_model) > 1 and base_model[0] == "o" and base_model[1].isdigit())


def _json_schema(value: Any) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise InvokeBadRequestError("JSON Schema must be valid JSON") from error
    if not isinstance(value, dict):
        raise InvokeBadRequestError("JSON Schema must be an object")
    value = value.copy()
    if "schema" not in value:
        value = {"schema": value}
    value.setdefault("name", "response")
    return {"type": "json_schema", **value}


def _input_content(value: Any) -> Any:
    if isinstance(value, str) or value is None:
        return value
    result = []
    for item in value:
        if isinstance(item, TextPromptMessageContent):
            result.append({"type": "input_text", "text": item.data})
        elif isinstance(item, ImagePromptMessageContent):
            if not item.url and not item.base64_data:
                raise InvokeBadRequestError("Image input must include data")
            result.append(
                {
                    "type": "input_image",
                    "image_url": item.data,
                    "detail": item.detail.value,
                }
            )
        elif isinstance(item, DocumentPromptMessageContent):
            if item.url:
                result.append({"type": "input_file", "file_url": item.url})
            elif item.base64_data:
                result.append(
                    {
                        "type": "input_file",
                        "filename": item.filename or f"document{item.format}",
                        "file_data": item.data,
                    }
                )
            else:
                raise InvokeBadRequestError("Document input must include data")
        elif item.type in (
            PromptMessageContentType.AUDIO,
            PromptMessageContentType.VIDEO,
        ):
            raise InvokeBadRequestError(
                f"{item.type.value} input requires Chat Completions"
            )
        else:
            raise InvokeBadRequestError(
                f"Unsupported Responses content: {item.type.value}"
            )
    return result


def field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    return copy.deepcopy(value)


def make_call(
    call_id: str,
    name: str,
    arguments: str,
) -> AssistantPromptMessage.ToolCall:
    return AssistantPromptMessage.ToolCall(
        id=call_id,
        type="function",
        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
            name=name,
            arguments=arguments,
        ),
    )


def raise_error(error: Any) -> None:
    code = field(error, "code") or "response_failed"
    message = field(error, "message") or "response failed"
    description = f"OpenAI {code}: {message}"
    if code == "rate_limit_exceeded":
        raise InvokeRateLimitError(description)
    if code in ("invalid_api_key", "insufficient_permissions"):
        raise InvokeAuthorizationError(description)
    if code in ("server_error", "vector_store_timeout", "response_failed"):
        raise InvokeServerUnavailableError(description)
    raise InvokeBadRequestError(description)


def raise_for_status(response: Any, *, allow_incomplete: bool = False) -> None:
    status = field(response, "status")
    if (error := field(response, "error")) is not None or status == "failed":
        raise_error(error)
    if status == "incomplete" and not allow_incomplete:
        reason = field(field(response, "incomplete_details"), "reason", "unknown")
        raise InvokeBadRequestError(f"OpenAI response incomplete: {reason}")
    if status in ("cancelled", "queued", "in_progress"):
        raise InvokeServerUnavailableError(
            f"Unexpected OpenAI response status: {status}"
        )
    if isinstance(status, str) and status not in ("completed", "incomplete"):
        raise InvokeServerUnavailableError(f"Unknown OpenAI response status: {status}")


def parameters(
    model: str,
    model_parameters: dict,
    tools: list[Any] | None,
    user: str | None,
) -> dict[str, Any]:
    params = model_parameters.copy()
    for name in ("presence_penalty", "frequency_penalty"):
        value = params.pop(name, None)
        if value not in (None, 0, 0.0):
            raise InvokeBadRequestError(f"{name} requires Chat Completions")
    if params.pop("seed", None) is not None:
        raise InvokeBadRequestError("seed requires Chat Completions")

    for old_name in ("max_tokens", "max_completion_tokens"):
        if old_name in params:
            params["max_output_tokens"] = params.pop(old_name)

    reasoning_value = params.pop("reasoning", None)
    if reasoning_value is None:
        reasoning = {}
    elif not isinstance(reasoning_value, dict):
        raise InvokeBadRequestError("reasoning must be an object")
    else:
        reasoning = reasoning_value.copy()
    for source, target in (
        ("reasoning_effort", "effort"),
        ("reasoning_summary", "summary"),
        ("reasoning_mode", "mode"),
        ("reasoning_context", "context"),
    ):
        value = params.pop(source, None)
        if value not in (None, ""):
            reasoning[target] = value
    if reasoning:
        params["reasoning"] = reasoning

    response_format = params.pop("response_format", None)
    schema = params.pop("json_schema", None)
    text_value = params.pop("text", None)
    if text_value is None:
        text = {}
    elif not isinstance(text_value, dict):
        raise InvokeBadRequestError("text must be an object")
    else:
        text = text_value.copy()
    if isinstance(response_format, dict):
        config = response_format.get("json_schema", response_format)
        text["format"] = (
            _json_schema(config)
            if response_format.get("type") == "json_schema"
            else {"type": response_format.get("type", "text")}
        )
    elif response_format:
        format_type = str(response_format).lower()
        text["format"] = (
            _json_schema(schema)
            if format_type == "json_schema"
            else {"type": format_type}
        )
    if (verbosity := params.pop("verbosity", None)) is not None:
        text["verbosity"] = verbosity
    if text:
        params["text"] = text

    choice = params.get("tool_choice")
    if isinstance(choice, dict) and choice.get("type") == "function":
        function = choice.get("function")
        if isinstance(function, dict) and function.get("name"):
            params["tool_choice"] = {"type": "function", "name": function["name"]}

    parameter_user = params.pop("user", None)
    identity = user or parameter_user
    if identity:
        digest = _user_digest(identity)
        params.setdefault("safety_identifier", digest)
        params.setdefault("prompt_cache_key", digest)

    params.setdefault("store", False)
    if params["store"] is False and _supports_encrypted_reasoning(model):
        include = list(params.get("include") or [])
        if "reasoning.encrypted_content" not in include:
            include.append("reasoning.encrypted_content")
        params["include"] = include
    if tools:
        params["tools"] = [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "strict": False,
            }
            for tool in tools
        ]
        params.setdefault("tool_choice", "auto")
    return params


def input_items(prompt_messages: list[PromptMessage]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for message in prompt_messages:
        if isinstance(
            message,
            (SystemPromptMessage, DeveloperPromptMessage, UserPromptMessage),
        ):
            value = _input_content(message.content)
            if value not in (None, "", []):
                result.append(
                    {
                        "type": "message",
                        "role": message.role.value,
                        "content": value,
                    }
                )
        elif isinstance(message, AssistantPromptMessage):
            if isinstance(message.opaque_body, dict):
                stored = message.opaque_body.get(OUTPUT_KEY)
                if isinstance(stored, list) and all(
                    isinstance(item, dict) for item in stored
                ):
                    result.extend(copy.deepcopy(stored))
                    continue
            value = _input_content(message.content)
            if value not in (None, "", []):
                result.append(
                    {"type": "message", "role": "assistant", "content": value}
                )
            result.extend(
                {
                    "type": "function_call",
                    "call_id": call.id,
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                }
                for call in message.tool_calls
            )
        elif isinstance(message, ToolPromptMessage):
            result.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": _input_content(message.content) or "",
                }
            )
        else:
            raise InvokeBadRequestError(
                f"Unsupported Responses message: {type(message).__name__}"
            )
    return result


def content(response: Any) -> str:
    parts: list[str] = []
    for item in field(response, "output", []) or []:
        item_type = field(item, "type")
        if item_type == "reasoning":
            summary = "".join(
                field(part, "text", "") or ""
                for part in field(item, "summary", []) or []
                if field(part, "type") in (None, "summary_text")
            )
            if summary:
                parts.append(f"<think>\n{summary}\n</think>\n")
        elif item_type == "message":
            item_content = field(item, "content", []) or []
            if isinstance(item_content, str):
                parts.append(item_content)
                continue
            for part in item_content:
                if field(part, "type") == "output_text":
                    parts.append(field(part, "text", "") or "")
                elif field(part, "type") == "refusal":
                    parts.append(field(part, "refusal", "") or "")
    return "".join(parts) or (field(response, "output_text", "") or "")


def response_calls(response: Any) -> list[AssistantPromptMessage.ToolCall]:
    calls = []
    for item in field(response, "output", []) or []:
        if field(item, "type") != "function_call" or field(item, "status") not in (
            None,
            "completed",
        ):
            continue
        calls.append(
            make_call(
                field(item, "call_id", "") or "",
                field(item, "name", "") or "",
                field(item, "arguments", "") or "",
            )
        )
    return calls


def opaque(response: Any) -> dict[str, Any]:
    return {OUTPUT_KEY: [dump(item) for item in field(response, "output", []) or []]}


def truncate(value: str, stop: list[str] | None) -> str:
    positions = [value.find(token) for token in stop or [] if token]
    positions = [position for position in positions if position >= 0]
    result = value[: min(positions)] if positions else value
    if result.count("<think>") > result.count("</think>"):
        result += "\n</think>\n"
    return result


def _usage(compute_usage: Any, response: Any) -> Any:
    response_usage = field(response, "usage")
    if response_usage is not None:
        prompt_tokens = field(response_usage, "input_tokens", 0)
        completion_tokens = field(response_usage, "output_tokens", 0)
    else:
        prompt_tokens = 0
        completion_tokens = 0
    return compute_usage(prompt_tokens, completion_tokens)


# ---------------------------------------------------------------------------
# Streaming helpers ported from openai/models/llm/stream.py
# ---------------------------------------------------------------------------

class StopBuffer:
    def __init__(self, stop: list[str] | None) -> None:
        self.tokens = [token for token in stop or [] if token]
        self.keep = max((len(token) for token in self.tokens), default=1) - 1
        self.pending = ""
        self.stopped = False

    def push(self, value: str) -> str:
        if self.stopped or not value:
            return ""
        if not self.tokens:
            return value
        self.pending += value
        positions = [self.pending.find(token) for token in self.tokens]
        positions = [position for position in positions if position >= 0]
        if positions:
            result = self.pending[: min(positions)]
            self.pending = ""
            self.stopped = True
            return result
        emit = len(self.pending) - self.keep
        if emit <= 0:
            return ""
        result, self.pending = self.pending[:emit], self.pending[emit:]
        return result

    def finish(self) -> str:
        if self.stopped:
            return ""
        result, self.pending = self.pending, ""
        return result


def _track_call(fragments: dict[int, dict[str, Any]], event: Any) -> None:
    event_type = field(event, "type", "")
    index = field(event, "output_index", -1)
    item = field(event, "item")
    if (
        event_type.startswith("response.output_item")
        and field(item, "type") != "function_call"
    ):
        return
    fragment = fragments.setdefault(
        index,
        {"id": "", "name": "", "arguments": "", "done": False},
    )
    if item is not None:
        fragment["id"] = (
            field(item, "call_id", fragment["id"]) or fragment["id"]
        )
        fragment["name"] = (
            field(item, "name", fragment["name"]) or fragment["name"]
        )
        fragment["arguments"] = (
            field(item, "arguments", fragment["arguments"])
            or fragment["arguments"]
        )
        fragment["done"] = event_type.endswith(".done") and field(
            item, "status"
        ) in (None, "completed")
    elif event_type.endswith(".delta"):
        fragment["arguments"] += field(event, "delta", "") or ""
    elif event_type.endswith(".done"):
        fragment["arguments"] = (
            field(event, "arguments", fragment["arguments"])
            or fragment["arguments"]
        )
        fragment["done"] = True


def _fragment_calls(
    fragments: dict[int, dict[str, Any]],
) -> list[AssistantPromptMessage.ToolCall]:
    return [
        make_call(item["id"], item["name"], item["arguments"])
        for _, item in sorted(fragments.items())
        if item["done"]
    ]


def _chunk(model: str, value: str) -> LLMResultChunk:
    return LLMResultChunk(
        model=model,
        delta=LLMResultChunkDelta(
            index=0,
            message=AssistantPromptMessage(content=value),
        ),
    )


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class AihubmixOpenAIResponses:
    def __init__(self, credentials: Mapping[str, Any]):
        self.client = OpenAI(**self._to_credential_kwargs(credentials))
        self.credentials = dict(credentials)

    def _to_credential_kwargs(self, credentials: Mapping[str, Any]) -> Mapping[str, Any]:
        api_url = (
            (
                credentials.get("api_url_custom")
                if credentials.get("api_url") == "__custom__"
                else credentials.get("api_url")
            )
            or "https://aihubmix.com"
        ).rstrip("/")
        return {
            "api_key": credentials["api_key"],
            "base_url": f"{api_url}/v1",
            "timeout": Timeout(315.0, read=300.0, write=10.0, connect=5.0),
            "max_retries": 1,
        }

    def create_llm_result(
        self,
        *,
        model: str,
        prompt_messages: Sequence[PromptMessage],
        model_parameters: Mapping[str, Any],
        compute_usage: Any,
        user: Optional[str] = None,
        tools: Optional[list[PromptMessageTool]] = None,
        stop: Optional[list[str]] = None,
    ) -> LLMResult:
        params = dict(model_parameters)
        params.pop("enable_stream", None)

        wrapped = parameters(model, params, tools, user)
        logger.info("Aihubmix Responses API request: model=%s", model)

        response = self.client.responses.create(
            model=model,
            input=cast(Any, input_items(list(prompt_messages))),
            extra_headers=APP_CODE_HEADER,
            **wrapped,
        )
        raise_for_status(response, allow_incomplete=True)
        raw_content = content(response)
        visible_content = truncate(raw_content, stop)
        stopped = visible_content != raw_content
        calls = (
            response_calls(response)
            if field(response, "status") == "completed" and not stopped
            else []
        )
        return LLMResult(
            model=field(response, "model", model),
            message=AssistantPromptMessage(
                content=visible_content,
                tool_calls=calls,
                opaque_body=None if stopped else opaque(response),
            ),
            usage=_usage(compute_usage, response),
        )

    def stream_llm_chunks(
        self,
        *,
        model: str,
        prompt_messages: Sequence[PromptMessage],
        model_parameters: Mapping[str, Any],
        compute_usage: Any,
        user: Optional[str] = None,
        tools: Optional[list[PromptMessageTool]] = None,
        stop: Optional[list[str]] = None,
    ) -> Generator[LLMResultChunk, None, None]:
        params = dict(model_parameters)
        params.pop("enable_stream", None)

        wrapped = parameters(model, params, tools, user)
        logger.info("Aihubmix Responses API stream request: model=%s", model)

        events = self.client.responses.create(
            model=model,
            input=cast(Any, input_items(list(prompt_messages))),
            stream=True,
            extra_headers=APP_CODE_HEADER,
            **wrapped,
        )
        buffer = StopBuffer(stop)
        formatted = ""
        thinking = False
        terminal = None
        incomplete_reason = None
        fragments: dict[int, dict[str, Any]] = {}

        try:
            for event in cast(Iterable[Any], events):
                event_type = field(event, "type", "")
                if event_type == "response.reasoning_summary_text.delta":
                    piece = field(event, "delta", "") or ""
                    if piece:
                        if not thinking:
                            piece = "<think>\n" + piece
                            thinking = True
                        formatted += piece
                        if visible := buffer.push(piece):
                            yield _chunk(model, visible)
                elif event_type in ("response.output_text.delta", "response.refusal.delta"):
                    piece = field(event, "delta", "") or ""
                    if piece:
                        if thinking:
                            piece = "\n</think>\n" + piece
                            thinking = False
                        formatted += piece
                        if visible := buffer.push(piece):
                            yield _chunk(model, visible)
                elif event_type.startswith(
                    "response.function_call_arguments."
                ) or event_type in (
                    "response.output_item.added",
                    "response.output_item.done",
                ):
                    _track_call(fragments, event)
                elif event_type == "response.completed":
                    terminal = field(event, "response")
                    raise_for_status(terminal)
                    break
                elif event_type == "response.incomplete":
                    terminal = field(event, "response")
                    raise_for_status(terminal, allow_incomplete=True)
                    incomplete_reason = field(
                        field(terminal, "incomplete_details"),
                        "reason",
                    )
                    break
                elif event_type == "response.failed":
                    raise_for_status(field(event, "response"))
                elif event_type == "error":
                    raise_error(event)
                elif event_type == "response.cancelled":
                    raise InvokeServerUnavailableError("OpenAI response was cancelled")
        finally:
            close = getattr(events, "close", None)
            if callable(close):
                close()

        if terminal is None:
            raise InvokeConnectionError(
                "OpenAI Responses stream ended without a terminal event"
            )

        if thinking:
            piece = "\n</think>\n"
            formatted += piece
            if buffer.stopped:
                yield _chunk(model, piece)
            elif visible := buffer.push(piece):
                yield _chunk(model, visible)

        canonical = content(terminal)
        if not formatted:
            formatted = canonical
            if visible := buffer.push(canonical):
                yield _chunk(model, visible)
        elif canonical.startswith(formatted):
            remainder = canonical[len(formatted) :]
            formatted += remainder
            if visible := buffer.push(remainder):
                yield _chunk(model, visible)
        if visible := buffer.finish():
            yield _chunk(model, visible)

        status = field(terminal, "status")
        calls = (
            response_calls(terminal)
            if status == "completed" and not buffer.stopped
            else []
        )
        if not calls and status == "completed" and not buffer.stopped:
            calls = _fragment_calls(fragments)
        finish_reason = {
            "max_output_tokens": "length",
            "content_filter": "content_filter",
        }.get(incomplete_reason, "incomplete" if status == "incomplete" else "stop")
        if calls:
            finish_reason = "tool_calls"
        if buffer.stopped:
            finish_reason = "stop"

        yield LLMResultChunk(
            model=field(terminal, "model", model),
            delta=LLMResultChunkDelta(
                index=0,
                message=AssistantPromptMessage(
                    content="",
                    tool_calls=calls,
                    opaque_body=None if buffer.stopped else opaque(terminal),
                ),
                finish_reason=finish_reason,
                usage=_usage(compute_usage, terminal),
            ),
        )
