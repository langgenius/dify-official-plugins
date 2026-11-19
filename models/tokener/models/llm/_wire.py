import json
import re

from dify_plugin.entities.model.llm import LLMResultChunk, LLMResultChunkDelta, LLMUsage
from dify_plugin.entities.model.message import AssistantPromptMessage
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

TRANSPORT_FIELDS = frozenset(
    {
        "api_key",
        "openai_api_key",
        "openai_api_base",
        "openai_organization",
        "anthropic_api_url",
        "anthropic_api_key",
        "google_api_key",
        "google_base_url",
        "dashscope_api_key",
        "route",
        "models",
        "model_id",
        "provider",
        "model_name",
        "authorization",
        "baseURL",
        "api_base",
        "base_url",
        "endpoint_url",
        "endpoint_model_name",
        "extra_headers",
        "headers",
        "credentials",
        "model",
        "messages",
        "input",
        "stream",
        "stream_options",
        "tools",
        "functions",
        "user",
        "metadata",
        "extra_body",
        "timeout",
        "max_retries",
        "custom_llm_provider",
        "api_version",
        "litellm_params",
        "drop_params",
        "allowed_openai_params",
        "additional_drop_params",
    }
)
_CONTROL_FIELDS = {name.lower() for name in TRANSPORT_FIELDS}


def reject_controls(value, *, nested: bool = True) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                not isinstance(key, str)
                or key.lower() in _CONTROL_FIELDS
                or key.lower().startswith(
                    ("litellm_", "_litellm", "proxy_", "x-goog-", "x-tokener-")
                )
            ):
                raise InvokeBadRequestError("Transport fields are not model parameters")
            if nested:
                reject_controls(item)
    elif isinstance(value, list):
        for item in value:
            reject_controls(item)


def json_object(value, name: str) -> dict:
    try:
        if isinstance(value, str):
            value = json.loads(value, parse_constant=_invalid_constant)
    except ValueError as error:
        raise InvokeBadRequestError(f"{name} must be a JSON object") from error
    if not isinstance(value, dict):
        raise InvokeBadRequestError(f"{name} must be a JSON object")
    return value.copy()


def _invalid_constant(value: str) -> None:
    raise ValueError("Invalid JSON constant")


def structured_format(parameters: dict) -> dict | None:
    value = parameters.pop("response_format", None)
    schema = parameters.pop("json_schema", None)
    if not value:
        if not schema:
            return None
        value = "json_schema"
    if isinstance(value, str):
        kind = value.lower()
        value = {"type": ("json_schema" if schema else "json_object") if kind == "json" else kind}
    if not isinstance(value, dict) or value.get("type") not in {
        "text",
        "json_object",
        "json_schema",
    }:
        raise InvokeBadRequestError("Unsupported response_format")
    reject_controls(value, nested=False)
    if value["type"] == "json_schema":
        schema = json_object(value.get("json_schema", schema), "json_schema")
        if "schema" not in schema:
            schema = {"schema": schema}
        reject_controls(schema, nested=False)
        if not isinstance(schema["schema"], dict):
            raise InvokeBadRequestError("json_schema must contain a schema object")
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                **{
                    key: schema[key]
                    for key in ("name", "description", "strict", "schema")
                    if key in schema
                },
            },
        }
    return {"type": value["type"]}


def tool_call(call_id: str, name: str, arguments: str | dict) -> AssistantPromptMessage.ToolCall:
    return AssistantPromptMessage.ToolCall(
        id=call_id,
        type="function",
        function=AssistantPromptMessage.ToolCall.ToolCallFunction(
            name=name,
            arguments=json.dumps(arguments, ensure_ascii=False)
            if isinstance(arguments, dict)
            else arguments,
        ),
    )


def is_object(arguments: str) -> bool:
    try:
        json_object(arguments, "Tool arguments")
    except InvokeBadRequestError:
        return False
    return True


def without_thinking(value: str) -> str:
    return re.sub(r"<think>.*?</think>\s*", "", value, flags=re.DOTALL)


def thinking_text(value: str) -> str:
    return f"<think>\n{value}\n</think>\n" if value else ""


def chunk(
    model: str,
    content: str | list = "",
    *,
    calls: list | None = None,
    opaque: dict | None = None,
    finish: str | None = None,
    usage: LLMUsage | None = None,
) -> LLMResultChunk:
    return LLMResultChunk(
        model=model,
        delta=LLMResultChunkDelta(
            index=0,
            message=AssistantPromptMessage(
                content=content, tool_calls=calls or [], opaque_body=opaque
            ),
            finish_reason=finish,
            usage=usage,
        ),
    )


def response_error(error: dict | None = None) -> None:
    error = error if isinstance(error, dict) else {}
    code = error.get("code") or error.get("type") or error.get("status")
    if code in ("rate_limit_exceeded", "rate_limit_error", 429):
        raise InvokeRateLimitError("Tokener.ai rate limit exceeded")
    if code in ("invalid_api_key", "insufficient_permissions", "authentication_error", 401, 403):
        raise InvokeAuthorizationError("Tokener.ai denied model access")
    if code in ("invalid_request_error", "invalid_request", 400):
        raise InvokeBadRequestError("Tokener.ai rejected the request")
    raise InvokeServerUnavailableError("Tokener.ai returned an error event")
