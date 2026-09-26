"""OpenAI Responses (/responses) protocol helpers for OpenCode Go.

Models like grok-4.7 / grok-4.6 / gpt-5.6-luna / muse-spark-* reject oa-compat and only
work on the Responses endpoint. Auth is Authorization Bearer + session + UA.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any, Optional

import requests
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    PromptMessage,
    PromptMessageContent,
    PromptMessageContentType,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    VideoPromptMessageContent,
)
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
try:
    from models.llm import friendly_errors
except ImportError:  # pragma: no cover - importlib standalone load
    import friendly_errors

DEFAULT_MAX_OUTPUT_TOKENS = 4096


def _content_to_responses_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, PromptMessageContent):
                if item.type == PromptMessageContentType.TEXT and isinstance(
                    item, TextPromptMessageContent
                ):
                    parts.append(item.data or "")
                elif isinstance(item, ImagePromptMessageContent):
                    parts.append(f"[image: {item.url or 'inline'}]")
                elif isinstance(item, VideoPromptMessageContent):
                    parts.append(f"[video: {item.url or 'inline'}]")
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
                elif item.get("type") == "image_url":
                    url = (item.get("image_url") or {}).get("url")
                    parts.append(f"[image: {url or 'inline'}]")
            else:
                parts.append(str(item))
        return "".join(parts)
    if isinstance(content, PromptMessageContent):
        if isinstance(content, TextPromptMessageContent):
            return content.data or ""
        return str(getattr(content, "url", "") or content)
    return str(content)


def build_input_payload(
    prompt_messages: list[PromptMessage],
) -> list[dict[str, Any]]:
    """Build Responses API `input` as a message list."""
    items: list[dict[str, Any]] = []
    for message in prompt_messages:
        if isinstance(message, SystemPromptMessage):
            text = _content_to_responses_text(message.content)
            if text:
                items.append({"role": "system", "content": text})
            continue

        if isinstance(message, ToolPromptMessage):
            text = _content_to_responses_text(message.content)
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": text or "",
                }
            )
            continue

        if isinstance(message, AssistantPromptMessage):
            text = _content_to_responses_text(message.content)
            if text:
                items.append({"role": "assistant", "content": text})
            for call in message.tool_calls or []:
                items.append(
                    {
                        "type": "function_call",
                        "call_id": call.id,
                        "name": call.function.name,
                        "arguments": call.function.arguments or "{}",
                    }
                )
            continue

        text = _content_to_responses_text(message.content)
        items.append({"role": "user", "content": text})
    return items


def build_tools_payload(
    tools: Optional[list[PromptMessageTool]],
) -> Optional[list[dict[str, Any]]]:
    if not tools:
        return None
    out: list[dict[str, Any]] = []
    for tool in tools:
        out.append(
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.parameters
                or {"type": "object", "properties": {}},
            }
        )
    return out or None


def filter_model_parameters(model_parameters: dict) -> dict[str, Any]:
    allowed = {
        "temperature": "temperature",
        "top_p": "top_p",
        "enable_thinking": "enable_thinking",
        "thinking_budget": "thinking_budget",
        "reasoning_effort": "reasoning_effort",
        "response_format": "response_format",
        "json_schema": "json_schema",
        "max_tokens": "max_output_tokens",
        "max_output_tokens": "max_output_tokens",
    }
    out: dict[str, Any] = {}
    for src, dst in allowed.items():
        if src in model_parameters and model_parameters[src] is not None:
            if dst not in out:
                out[dst] = model_parameters[src]
    if "max_output_tokens" not in out:
        out["max_output_tokens"] = DEFAULT_MAX_OUTPUT_TOKENS
    return out


def map_http_error(response: requests.Response, body_text: str) -> Exception:
    return friendly_errors.map_http_error(
        response.status_code, body_text, protocol="Responses"
    )


def _text_from_output_item(item: dict[str, Any]) -> str:
    if item.get("type") == "message" or item.get("role") == "assistant":
        content = item.get("content") or []
        if isinstance(content, str):
            return content
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                parts.append(str(block))
                continue
            if block.get("type") in {"output_text", "text"}:
                parts.append(block.get("text") or "")
            elif block.get("text"):
                parts.append(str(block.get("text")))
        return "".join(parts)
    if item.get("type") == "output_text":
        return item.get("text") or ""
    return ""


def _tool_calls_from_output(output: list[Any]) -> list[AssistantPromptMessage.ToolCall]:
    tool_calls: list[AssistantPromptMessage.ToolCall] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"function_call", "tool_call"}:
            tool_calls.append(
                AssistantPromptMessage.ToolCall(
                    id=item.get("call_id") or item.get("id") or "",
                    type="function",
                    function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                        name=item.get("name") or "",
                        arguments=item.get("arguments") or "{}",
                    ),
                )
            )
    return tool_calls


def parse_non_stream_response(
    data: dict[str, Any],
) -> tuple[str, list[AssistantPromptMessage.ToolCall], int, int, Optional[str]]:
    output = data.get("output") or []
    if not output and data.get("output_text"):
        text = data.get("output_text") or ""
        usage = data.get("usage") or {}
        return (
            text,
            [],
            int(usage.get("input_tokens") or 0),
            int(usage.get("output_tokens") or 0),
            data.get("status"),
        )

    text = "".join(_text_from_output_item(item) for item in output if isinstance(item, dict))
    tool_calls = _tool_calls_from_output(output)
    usage = data.get("usage") or {}
    status = data.get("status")
    if not status and data.get("incomplete_details"):
        status = "incomplete"
    return (
        text,
        tool_calls,
        int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
        int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
        status,
    )


def parse_stream_response(
    response: requests.Response,
) -> Generator[dict[str, Any], None, None]:
    """Yield protocol events for the caller to wrap.

    Dicts:
      {"kind": "text_delta", "text": str}
      {"kind": "tool_call_delta", "id", "name", "arguments_delta"}
      {"kind": "usage", "input_tokens", "output_tokens"}
      {"kind": "stop", "stop_reason"}
      {"kind": "error", "message"}
    """
    state: dict[str, Any] = {
        "stopped": False,
        "usage": None,
    }

    def parse_sse_data(raw: str) -> Optional[dict[str, Any]]:
        data_payload = None
        for line in raw.splitlines():
            if line.startswith("data:"):
                data_payload = line[5:].lstrip()
        if data_payload is None:
            data_payload = raw.strip()
        if not data_payload:
            return None
        try:
            return json.loads(data_payload)
        except json.JSONDecodeError:
            return None

    def dispatch(data: dict[str, Any]) -> Generator[dict[str, Any], None, None]:
        etype = data.get("type") or ""
        if etype in {"response.output_text.delta", "response.text.delta"}:
            text = data.get("delta") or data.get("text") or ""
            if text:
                yield {"kind": "text_delta", "text": text}
            return
        if etype == "response.output_item.added":
            item = data.get("item") or {}
            if item.get("type") in {"function_call", "tool_call"}:
                yield {
                    "kind": "tool_call_delta",
                    "index": data.get("output_index") or 0,
                    "id": item.get("call_id") or item.get("id") or "",
                    "name": item.get("name") or "",
                    "arguments_delta": "",
                }
            return
        if etype == "response.function_call_arguments.delta":
            yield {
                "kind": "tool_call_delta",
                "index": data.get("output_index") or 0,
                "id": data.get("call_id") or "",
                "name": "",
                "arguments_delta": data.get("delta") or "",
            }
            return
        if etype in {"response.completed", "response.incomplete", "response.failed"}:
            if state.get("stopped"):
                return
            resp = data.get("response") or {}
            usage = resp.get("usage") or {}
            in_tok = int(usage.get("input_tokens") or 0)
            out_tok = int(usage.get("output_tokens") or 0)
            state["usage"] = {"input_tokens": in_tok, "output_tokens": out_tok}
            if in_tok or out_tok:
                yield {
                    "kind": "usage",
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                }
            stop_reason = (
                resp.get("status")
                or ("incomplete" if etype == "response.incomplete" else "completed")
            )
            if etype == "response.failed":
                err = data.get("error") or resp.get("error") or {}
                message = err.get("message") if isinstance(err, dict) else str(err or data)
                yield {"kind": "error", "message": message}
            state["stopped"] = True
            yield {"kind": "stop", "stop_reason": stop_reason}
            return
        if etype == "error":
            err = data.get("error") or data.get("response", {}).get("error") or {}
            yield {
                "kind": "error",
                "message": err.get("message") if isinstance(err, dict) else str(err or data),
            }

    buffer = ""
    # Force UTF-8: requests may default to ISO-8859-1 when Content-Type has no charset.
    for chunk in response.iter_lines(decode_unicode=False):
        if chunk is None:
            continue
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8", errors="replace")
        else:
            chunk = str(chunk)
        if chunk == "":
            if not buffer.strip():
                continue
            raw = buffer
            buffer = ""
            data = parse_sse_data(raw)
            if data is not None:
                yield from dispatch(data)
            continue
        buffer += chunk + "\n"

    if buffer.strip():
        data = parse_sse_data(buffer)
        if data is not None:
            yield from dispatch(data)

    if not state.get("stopped"):
        usage = state.get("usage")
        if usage and (usage.get("input_tokens") or usage.get("output_tokens")):
            yield {
                "kind": "usage",
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
            }
        yield {"kind": "stop", "stop_reason": "completed"}
