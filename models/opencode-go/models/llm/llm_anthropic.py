"""Anthropic Messages (/messages) protocol helpers for OpenCode Go.

OpenCode's Zen Go gateway exposes selected models (e.g. union-alpha) only on
Anthropic Messages. Auth is x-api-key (not Bearer). Session header is required.
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

DEFAULT_MAX_TOKENS = 4096


def _content_to_anthropic_blocks(content: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if content is None:
        return blocks
    if isinstance(content, str):
        if content:
            blocks.append({"type": "text", "text": content})
        return blocks

    items: list[Any]
    if isinstance(content, list):
        items = content
    else:
        items = [content]

    for item in items:
        if isinstance(item, str):
            if item:
                blocks.append({"type": "text", "text": item})
            continue
        if isinstance(item, PromptMessageContent):
            if item.type == PromptMessageContentType.TEXT and isinstance(
                item, TextPromptMessageContent
            ):
                if item.data:
                    blocks.append({"type": "text", "text": item.data})
            elif isinstance(item, ImagePromptMessageContent):
                # OpenCode gateways often accept base64 image blocks; keep text
                # fallback so vision-unavailable models still receive a marker.
                if item.url:
                    blocks.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": item.url,
                            },
                        }
                    )
                elif getattr(item, "base64", None):
                    blocks.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": getattr(item, "mime_type", None)
                                or "image/png",
                                "data": item.base64,
                            },
                        }
                    )
            elif isinstance(item, VideoPromptMessageContent):
                if item.url:
                    blocks.append(
                        {"type": "text", "text": f"[video: {item.url}]"}
                    )
            continue
        if isinstance(item, dict):
            if item.get("type") == "text" and item.get("text"):
                blocks.append({"type": "text", "text": str(item["text"])})
            elif item.get("type") == "image_url":
                url = (item.get("image_url") or {}).get("url")
                if url:
                    blocks.append(
                        {"type": "image", "source": {"type": "url", "url": url}}
                    )
            continue
        text = str(item)
        if text:
            blocks.append({"type": "text", "text": text})
    return blocks


def _normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fold consecutive same-role turns and drop empty text blocks.

    Anthropic Messages requires alternating roles and rejects empty text blocks.
    """
    normalized: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content") or []
        if isinstance(content, list):
            content = [
                b
                for b in content
                if not (
                    isinstance(b, dict)
                    and b.get("type") == "text"
                    and not (b.get("text") or "").strip()
                )
            ]
        if not content:
            # Tool-only assistant messages still need a non-empty content list.
            if msg.get("role") == "assistant":
                content = [{"type": "text", "text": " "}]
            else:
                content = [{"type": "text", "text": " "}]
        msg = {**msg, "content": content}

        if normalized and normalized[-1]["role"] == msg["role"]:
            prev = normalized[-1]["content"]
            if isinstance(prev, list) and isinstance(msg["content"], list):
                # Placeholder " " text is replaced by real blocks when folding.
                if (
                    len(prev) == 1
                    and prev[0].get("type") == "text"
                    and prev[0].get("text") == " "
                ):
                    normalized[-1] = msg
                else:
                    normalized[-1] = {
                        **normalized[-1],
                        "content": [*prev, *msg["content"]],
                    }
                continue
        normalized.append(msg)
    return normalized


def build_messages_payload(
    prompt_messages: list[PromptMessage],
) -> tuple[Optional[str], list[dict[str, Any]]]:
    """Return (system, anthropic messages). System is a separate field."""
    system_parts: list[str] = []
    messages: list[dict[str, Any]] = []

    for message in prompt_messages:
        if isinstance(message, SystemPromptMessage):
            system_parts.extend(
                b["text"]
                for b in _content_to_anthropic_blocks(message.content)
                if b.get("type") == "text"
            )
            continue

        if isinstance(message, ToolPromptMessage):
            tool_content = message.content
            if not isinstance(tool_content, str):
                blocks = _content_to_anthropic_blocks(tool_content)
                tool_content = "\n".join(
                    b.get("text", "") for b in blocks if b.get("type") == "text"
                )
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": message.tool_call_id,
                            "content": tool_content or "",
                        }
                    ],
                }
            )
            continue

        if isinstance(message, AssistantPromptMessage):
            blocks = _content_to_anthropic_blocks(message.content)
            for call in message.tool_calls or []:
                arguments = call.function.arguments or "{}"
                try:
                    parsed = json.loads(arguments) if arguments else {}
                except json.JSONDecodeError:
                    parsed = {"_raw": arguments}
                if not isinstance(parsed, dict):
                    parsed = {"value": parsed}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call.id,
                        "name": call.function.name,
                        "input": parsed,
                    }
                )
            messages.append({"role": "assistant", "content": blocks})
            continue

        # user (default)
        blocks = _content_to_anthropic_blocks(message.content)
        messages.append({"role": "user", "content": blocks})

    system = "\n\n".join(p for p in system_parts if p) or None
    return system, _normalize_messages(messages)


def build_tools_payload(
    tools: Optional[list[PromptMessageTool]],
) -> Optional[list[dict[str, Any]]]:
    if not tools:
        return None
    out: list[dict[str, Any]] = []
    for tool in tools:
        out.append(
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.parameters
                or {"type": "object", "properties": {}},
            }
        )
    return out or None


def filter_model_parameters(model_parameters: dict) -> dict[str, Any]:
    allowed = {
        "temperature": "temperature",
        "top_p": "top_p",
        "top_k": "top_k",
        "max_tokens": "max_tokens",
        "stop_sequences": "stop_sequences",
    }
    out: dict[str, Any] = {}
    for src, dst in allowed.items():
        if src in model_parameters and model_parameters[src] is not None:
            out[dst] = model_parameters[src]
    if "max_tokens" not in out:
        out["max_tokens"] = DEFAULT_MAX_TOKENS
    return out


def map_http_error(response: requests.Response, body_text: str) -> Exception:
    status = response.status_code
    snippet = (body_text or "")[:500]
    lowered = snippet.lower()
    if "unsupported_country_region_territory" in lowered or "region" in lowered and "not supported" in lowered:
        return InvokeAuthorizationError(
            f"OpenCode Anthropic Messages blocked by region policy ({status}): {snippet}"
        )
    if status in (401, 403):
        return InvokeAuthorizationError(
            f"OpenCode Anthropic Messages auth failed ({status}): {snippet}"
        )
    if status == 429:
        return InvokeRateLimitError(
            f"OpenCode Anthropic Messages rate limited: {snippet}"
        )
    if status == 400:
        return InvokeBadRequestError(
            f"OpenCode Anthropic Messages bad request ({status}): {snippet}"
        )
    if status >= 500:
        return InvokeServerUnavailableError(
            f"OpenCode Anthropic Messages server error ({status}): {snippet}"
        )
    return InvokeBadRequestError(
        f"OpenCode Anthropic Messages HTTP {status}: {snippet}"
    )


def parse_non_stream_response(
    data: dict[str, Any],
) -> tuple[str, list[AssistantPromptMessage.ToolCall], int, int, Optional[str]]:
    """Return (text, tool_calls, input_tokens, output_tokens, stop_reason)."""
    text_parts: list[str] = []
    tool_calls: list[AssistantPromptMessage.ToolCall] = []
    for block in data.get("content") or []:
        btype = block.get("type")
        if btype == "text":
            text_parts.append(block.get("text") or "")
        elif btype == "tool_use":
            tool_calls.append(
                AssistantPromptMessage.ToolCall(
                    id=block.get("id") or "",
                    type="function",
                    function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                        name=block.get("name") or "",
                        arguments=json.dumps(block.get("input") or {}, ensure_ascii=False),
                    ),
                )
            )
    usage = data.get("usage") or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    stop_reason = data.get("stop_reason")
    return "".join(text_parts), tool_calls, input_tokens, output_tokens, stop_reason


def _iter_sse_json_lines(raw: str) -> Generator[tuple[str, dict[str, Any]], None, None]:
    """Yield (event_type, data) from an SSE buffer."""
    event_name = ""
    data_lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif line.strip() == "":
            if data_lines:
                payload = "\n".join(data_lines)
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    parsed = {}
                etype = parsed.get("type") or event_name
                if etype:
                    yield etype, parsed
            event_name = ""
            data_lines = []
    if data_lines:
        payload = "\n".join(data_lines)
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = {}
        etype = parsed.get("type") or event_name
        if etype:
            yield etype, parsed


def parse_stream_response(
    response: requests.Response,
    prompt_messages: list[PromptMessage],
) -> Generator[dict[str, Any], None, None]:
    """Yield raw protocol events as dicts for the caller to wrap.

    Dicts:
      {"kind": "text_delta", "text": str}
      {"kind": "tool_call_delta", "id", "name", "arguments_delta"}
      {"kind": "usage", "input_tokens", "output_tokens"}
      {"kind": "stop", "stop_reason"}
      {"kind": "error", "message"}
    """
    del prompt_messages  # kept for API symmetry with callers
    state: dict[str, Any] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "tool_index_state": {},
        "stopped": False,
    }

    def dispatch(etype: str, data: dict[str, Any]) -> Generator[dict[str, Any], None, None]:
        if etype == "message_start":
            usage = (data.get("message") or {}).get("usage") or {}
            state["input_tokens"] = int(usage.get("input_tokens") or state["input_tokens"])
            state["output_tokens"] = int(
                usage.get("output_tokens") or state["output_tokens"]
            )
            return
        if etype == "content_block_delta":
            delta = data.get("delta") or {}
            dtype = delta.get("type")
            if dtype == "text_delta":
                text = delta.get("text") or ""
                if text:
                    yield {"kind": "text_delta", "text": text}
            elif dtype == "input_json_delta":
                idx = int(data.get("index") or 0)
                tool_state = state["tool_index_state"].setdefault(
                    idx, {"id": "", "name": "", "arguments": ""}
                )
                tool_state["arguments"] += delta.get("partial_json") or ""
                yield {
                    "kind": "tool_call_delta",
                    "index": idx,
                    "id": tool_state["id"],
                    "name": tool_state["name"],
                    "arguments_delta": delta.get("partial_json") or "",
                }
            return
        if etype == "content_block_start":
            block = data.get("content_block") or {}
            idx = int(data.get("index") or 0)
            if block.get("type") == "tool_use":
                state["tool_index_state"][idx] = {
                    "id": block.get("id") or "",
                    "name": block.get("name") or "",
                    "arguments": "",
                }
                yield {
                    "kind": "tool_call_delta",
                    "index": idx,
                    "id": block.get("id") or "",
                    "name": block.get("name") or "",
                    "arguments_delta": "",
                }
            return
        if etype == "message_delta":
            usage = data.get("usage") or {}
            state["output_tokens"] = int(
                usage.get("output_tokens") or state["output_tokens"]
            )
            # Capture stop_reason here but only emit finish on message_stop
            # so usage is finalized first and we never double-stop.
            stop_reason = (data.get("delta") or {}).get("stop_reason")
            if stop_reason:
                state["pending_stop_reason"] = stop_reason
            return
        if etype == "message_stop":
            if state.get("stopped"):
                return
            if state["input_tokens"] or state["output_tokens"]:
                yield {
                    "kind": "usage",
                    "input_tokens": state["input_tokens"],
                    "output_tokens": state["output_tokens"],
                }
            state["stopped"] = True
            yield {
                "kind": "stop",
                "stop_reason": state.get("pending_stop_reason") or "end_turn",
            }
            return
        if etype == "error":
            err = data.get("error") or {}
            yield {
                "kind": "error",
                "message": err.get("message") or data.get("message") or str(data),
            }

    buffer = ""
    for chunk in response.iter_lines(decode_unicode=True):
        if chunk is None:
            continue
        if isinstance(chunk, bytes):
            try:
                chunk = chunk.decode("utf-8")
            except UnicodeDecodeError:
                chunk = chunk.decode("utf-8", errors="replace")
        if chunk == "":
            if not buffer.strip():
                continue
            events = list(_iter_sse_json_lines(buffer))
            buffer = ""
            for etype, data in events:
                yield from dispatch(etype, data)
            continue
        buffer += chunk + "\n"

    if buffer.strip():
        for etype, data in _iter_sse_json_lines(buffer):
            yield from dispatch(etype, data)

    if not state.get("stopped"):
        if state["input_tokens"] or state["output_tokens"]:
            yield {
                "kind": "usage",
                "input_tokens": state["input_tokens"],
                "output_tokens": state["output_tokens"],
            }
        yield {
            "kind": "stop",
            "stop_reason": state.get("pending_stop_reason") or "end_turn",
        }
