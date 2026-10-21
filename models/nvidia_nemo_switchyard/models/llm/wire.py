"""Wire conversion: Dify prompt messages -> Switchyard IR -> Chat Completions / Responses streams."""

import json
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    DeveloperPromptMessage,
    PromptMessage,
    PromptMessageContentType,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
)

ApiFormat = Literal["chat_completions", "responses"]
PATHS: dict[str, str] = {"chat_completions": "/chat/completions", "responses": "/responses"}

# Reasoning this plugin streamed earlier comes back in the history wrapped in <think> tags.
_THINK = re.compile(r"^\s*<think>(.*?)</think>\s*", re.DOTALL)


class UpstreamError(Exception):
    """An upstream rejected or failed a request."""


class UpstreamAuthError(UpstreamError):
    pass


class UpstreamRateLimitError(UpstreamError):
    pass


class UpstreamServerError(UpstreamError):
    pass


class UpstreamBadRequestError(UpstreamError):
    pass


def _http_error(status: int, body: str) -> UpstreamError:
    message = f"HTTP {status}: {body}"
    if status in (401, 403):
        return UpstreamAuthError(message)
    if status == 429:
        return UpstreamRateLimitError(message)
    if status >= 500:
        return UpstreamServerError(message)
    return UpstreamBadRequestError(message)


@dataclass(frozen=True)
class Upstream:
    """One tier's upstream: a compatible API endpoint, model, and wire format."""

    endpoint_url: str
    api_key: str
    model: str
    api_format: ApiFormat
    # Responses API only: the `reasoning.summary` level to request, or None to omit it.
    reasoning_summary: str | None = None
    # Chat Completions only: the field that carries Max Tokens. Some reasoning models accept
    # only `max_completion_tokens` and reject `max_tokens`.
    token_param: str = "max_tokens"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class Delta:
    """One normalized piece of an upstream stream."""

    text: str = ""
    reasoning: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: tuple[int, int] | None = None
    finish_reason: str | None = None


def _text(message: PromptMessage) -> str:
    if message.content is None or isinstance(message.content, str):
        return message.content or ""
    parts = []
    for content in message.content:
        if content.type != PromptMessageContentType.TEXT:
            raise ValueError(f"Switchyard plugin supports text content only, got {content.type}")
        assert isinstance(content, TextPromptMessageContent)
        parts.append(content.data)
    return "".join(parts)


def _arguments(raw: str) -> Any:
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return raw


def to_ir(prompt_messages: Sequence[PromptMessage]) -> dict:
    """Convert Dify prompt messages to Switchyard's neutral request IR."""
    instructions: list[dict] = []
    messages: list[dict] = []
    for message in prompt_messages:
        text = _text(message)
        if isinstance(message, SystemPromptMessage | DeveloperPromptMessage):
            instructions.append(
                {"role": message.role.value, "content": [{"type": "text", "text": text}]}
            )
        elif isinstance(message, ToolPromptMessage):
            result = {
                "type": "tool_result",
                "tool_call_id": message.tool_call_id,
                "content": [{"type": "text", "text": text}],
                "is_error": None,
            }
            messages.append({"role": "tool", "content": [result]})
        elif isinstance(message, AssistantPromptMessage):
            blocks: list[dict] = []
            if match := _THINK.match(text):
                blocks.append({"type": "reasoning", "text": match.group(1).strip(), "signature": None})
                text = text[match.end() :]
            if text:
                blocks.append({"type": "text", "text": text})
            blocks += [
                {
                    "type": "tool_call",
                    "id": call.id,
                    "name": call.function.name,
                    "arguments": _arguments(call.function.arguments),
                }
                for call in message.tool_calls
            ]
            messages.append({"role": "assistant", "content": blocks})
        else:
            messages.append({"role": "user", "content": [{"type": "text", "text": text}]})
    return {"model": "switchyard", "instructions": instructions, "messages": messages}


def _block_text(blocks: list[dict], kind: str = "text") -> str:
    return "\n".join(b["text"] for b in blocks if b.get("type") == kind)


def _instructions(ir: dict) -> str:
    return "\n".join(_block_text(block["content"]) for block in ir.get("instructions", []))


def _dump(arguments: Any) -> str:
    return arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False)


def chat_body(
    ir: dict,
    model: str,
    tools: list[PromptMessageTool] | None,
    params: dict,
    stop: list[str] | None,
    token_param: str = "max_tokens",
) -> dict:
    """Chat Completions body from the IR."""
    messages: list[dict] = []
    if instructions := _instructions(ir):
        messages.append({"role": "system", "content": instructions})
    for message in ir["messages"]:
        blocks = message["content"]
        if message["role"] == "tool":
            messages += [
                {
                    "role": "tool",
                    "tool_call_id": b["tool_call_id"],
                    "content": _block_text(b["content"]),
                }
                for b in blocks
                if b["type"] == "tool_result"
            ]
            continue
        out: dict = {"role": message["role"], "content": _block_text(blocks) or None}
        tool_calls = [
            {
                "id": b["id"],
                "type": "function",
                "function": {"name": b["name"], "arguments": _dump(b["arguments"])},
            }
            for b in blocks
            if b["type"] == "tool_call"
        ]
        if tool_calls:
            out["tool_calls"] = tool_calls
            # `reasoning_content` is the common Chat Completions extension for reasoning.
            # Some thinking-mode servers require it on assistant turns that called tools;
            # servers without the extension ignore it.
            out["reasoning_content"] = _block_text(blocks, "reasoning")
        messages.append(out)

    body: dict = {"model": model, "messages": messages}
    if tools:
        body["tools"] = [
            {
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
            }
            for t in tools
        ]
    for name in ("temperature", "top_p"):
        if name in params:
            body[name] = params[name]
    if "max_tokens" in params:
        body[token_param] = params["max_tokens"]
    if stop:
        body["stop"] = stop
    return body


def responses_body(
    ir: dict,
    model: str,
    tools: list[PromptMessageTool] | None,
    params: dict,
    reasoning_summary: str | None = None,
) -> dict:
    """Responses body from the IR. The Responses API has no `stop` parameter."""
    # Instructions go into `input` as role messages, not the `instructions` field: a prompt
    # with only a system message would otherwise send an empty `input`, which is rejected.
    items: list[dict] = [
        {"role": block["role"], "content": text}
        for block in ir.get("instructions", [])
        if (text := _block_text(block["content"]))
    ]
    for message in ir["messages"]:
        for b in message["content"]:
            if b["type"] == "text":
                items.append({"role": message["role"], "content": b["text"]})
            elif b["type"] == "tool_call":
                items.append(
                    {
                        "type": "function_call",
                        "call_id": b["id"],
                        "name": b["name"],
                        "arguments": _dump(b["arguments"]),
                    }
                )
            elif b["type"] == "tool_result":
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": b["tool_call_id"],
                        "output": _block_text(b["content"]),
                    }
                )

    body: dict = {"model": model, "input": items}
    # Reasoning models stream reasoning text only when a summary is requested, but models
    # without reasoning summaries can reject the field, so it is sent only when enabled.
    if reasoning_summary:
        body["reasoning"] = {"summary": reasoning_summary}
    if tools:
        body["tools"] = [
            {
                "type": "function",
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
                # Dify tool schemas are not written for strict mode.
                "strict": False,
            }
            for t in tools
        ]
    for name in ("temperature", "top_p"):
        if name in params:
            body[name] = params[name]
    if "max_tokens" in params:
        body["max_output_tokens"] = params["max_tokens"]
    return body


def open_stream(
    upstream: Upstream,
    ir: dict,
    tools: list[PromptMessageTool] | None,
    params: dict,
    stop: list[str] | None,
) -> Iterator[Delta]:
    """Send the request and return its normalized stream.

    The HTTP request is made before this returns, so connection and HTTP errors raise here.
    That lets the caller fall back to the next candidate before any output is produced.
    """
    if upstream.api_format == "responses":
        body = responses_body(ir, upstream.model, tools, params, upstream.reasoning_summary)
        parse = _responses_deltas
    else:
        body = chat_body(ir, upstream.model, tools, params, stop, upstream.token_param)
        body["stream_options"] = {"include_usage": True}
        parse = _chat_deltas
    body["stream"] = True

    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if upstream.api_key:
        headers["Authorization"] = f"Bearer {upstream.api_key}"
    client = httpx.Client(timeout=httpx.Timeout(300, connect=10))
    try:
        request = client.build_request(
            "POST", upstream.endpoint_url + PATHS[upstream.api_format], json=body, headers=headers
        )
        response = client.send(request, stream=True)
        if response.status_code >= 400:
            detail = response.read().decode(errors="replace")[:500]
            raise _http_error(response.status_code, detail)
    except BaseException:
        client.close()
        raise
    return _closing(parse(_sse(response)), client)


def _closing(deltas: Iterator[Delta], client: httpx.Client) -> Iterator[Delta]:
    try:
        yield from deltas
    finally:
        client.close()


def _sse(response: httpx.Response) -> Iterator[dict]:
    """JSON payloads of a server-sent event stream. Event names are also in the payloads."""
    for line in response.iter_lines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        if data:
            try:
                yield json.loads(data)
            except json.JSONDecodeError as e:
                raise UpstreamServerError(f"invalid stream event: {data[:200]}") from e


def _chat_deltas(events: Iterator[dict]) -> Iterator[Delta]:
    calls: dict[int, ToolCall] = {}
    finish_reason = None
    for chunk in events:
        if error := chunk.get("error"):
            raise UpstreamServerError(json.dumps(error)[:500])
        if usage := chunk.get("usage"):
            yield Delta(usage=(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)))
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            text = (delta.get("content") or "") + (delta.get("refusal") or "")
            reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
            if text or reasoning:
                yield Delta(text=text, reasoning=reasoning)
            for part in delta.get("tool_calls") or []:
                call = calls.setdefault(part.get("index", 0), ToolCall("", "", ""))
                call.id = part.get("id") or call.id
                function = part.get("function") or {}
                call.name = function.get("name") or call.name
                call.arguments += function.get("arguments") or ""
            finish_reason = choice.get("finish_reason") or finish_reason
    if finish_reason is None:
        raise UpstreamServerError("stream ended without a finish_reason")
    # Truncated output can cut tool-call arguments short, so never publish those calls.
    # Other reasons keep them: some compatible servers report `stop` for tool calls.
    if calls and finish_reason != "length":
        yield Delta(tool_calls=[calls[i] for i in sorted(calls)])
    yield Delta(finish_reason=finish_reason)


def _responses_deltas(events: Iterator[dict]) -> Iterator[Delta]:
    calls: list[ToolCall] = []
    terminal = None
    for event in events:
        kind = event.get("type")
        if kind in ("response.output_text.delta", "response.refusal.delta"):
            yield Delta(text=event["delta"])
        elif kind == "response.reasoning_summary_text.delta":
            yield Delta(reasoning=event["delta"])
        elif kind == "response.reasoning_summary_part.added" and event.get("summary_index", 0) > 0:
            yield Delta(reasoning="\n\n")
        elif kind == "response.output_item.done" and event["item"]["type"] == "function_call":
            item = event["item"]
            calls.append(ToolCall(item["call_id"], item["name"], item["arguments"]))
        elif kind in ("response.completed", "response.incomplete"):
            terminal = kind
            if usage := event["response"].get("usage"):
                yield Delta(usage=(usage.get("input_tokens", 0), usage.get("output_tokens", 0)))
        elif kind in ("response.failed", "error"):
            raise UpstreamServerError(f"upstream {kind}: {json.dumps(event)[:500]}")
    if terminal is None:
        raise UpstreamServerError("stream ended before the response completed")
    if terminal == "response.incomplete":
        # Calls from a cut-off response may be incomplete, so they are not published.
        yield Delta(finish_reason="length")
    elif calls:
        yield Delta(tool_calls=calls)
        yield Delta(finish_reason="tool_calls")
    else:
        yield Delta(finish_reason="stop")
