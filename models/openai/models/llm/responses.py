from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any, cast

from openai import OpenAI

from dify_plugin.entities.model.llm import LLMResult
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
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

from ..common_openai import _user_digest
from . import tokens

if TYPE_CHECKING:
    from .llm import OpenAILargeLanguageModel

OUTPUT_KEY = "responses_output"


def generate(
    llm: OpenAILargeLanguageModel,
    client: OpenAI,
    model: str,
    credentials: dict,
    prompt_messages: list[PromptMessage],
    model_parameters: dict,
    tools: list[PromptMessageTool] | None,
    stop: list[str] | None,
    user: str | None,
) -> LLMResult:
    response = client.responses.create(
        model=model,
        input=cast(Any, input_items(prompt_messages)),
        **parameters(model, model_parameters, tools, user),
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
        usage=usage(
            llm,
            model,
            credentials,
            prompt_messages,
            tools,
            response,
            raw_content,
            calls,
        ),
    )


def parameters(
    model: str,
    model_parameters: dict,
    tools: list[PromptMessageTool] | None,
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


def _supports_encrypted_reasoning(model: str) -> bool:
    base_model = model.split(":", 2)[1] if model.startswith("ft:") else model
    return (
        base_model.startswith("gpt-5") and not base_model.endswith("-chat-latest")
    ) or (len(base_model) > 1 and base_model[0] == "o" and base_model[1].isdigit())


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


def usage(
    llm: OpenAILargeLanguageModel,
    model: str,
    credentials: dict,
    prompt_messages: list[PromptMessage],
    tools: list[PromptMessageTool] | None,
    response: Any,
    output: str,
    calls: list[AssistantPromptMessage.ToolCall],
) -> Any:
    response_usage = field(response, "usage")
    if response_usage is not None:
        prompt_tokens = field(response_usage, "input_tokens", 0)
        completion_tokens = field(response_usage, "output_tokens", 0)
    else:
        prompt_tokens = tokens.count_messages(model, prompt_messages, tools)
        completion_tokens = tokens.count_text(
            model,
            output + "".join(call.function.arguments for call in calls),
        )
    return llm._calc_response_usage(
        model,
        credentials,
        prompt_tokens,
        completion_tokens,
    )


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


def field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    return copy.deepcopy(value)


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
