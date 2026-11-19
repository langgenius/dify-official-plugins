import json
from collections.abc import Generator
from hashlib import sha256

from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    DocumentPromptMessageContent,
    ImagePromptMessageContent,
    TextPromptMessageContent,
    ToolPromptMessage,
)
from dify_plugin.errors.model import (
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeServerUnavailableError,
)

from models.llm import _sse, _wire

OUTPUT_KEY = "responses_output"
THINK_START = "<think>\n"
THINK_END = "\n</think>\n"
NON_STREAMING = {"gpt-5.5-pro", "gpt-5.5-pro-2026-04-23", "o3-pro"}
FIELDS = {
    "max_tokens",
    "max_output_tokens",
    "max_completion_tokens",
    "temperature",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
    "reasoning_effort",
    "reasoning_summary",
    "reasoning_mode",
    "reasoning_context",
    "verbosity",
    "service_tier",
    "parallel_tool_calls",
    "response_format",
    "json_schema",
    "enable_stream",
    "tool_choice",
    "top_logprobs",
    "logprobs",
}
SAMPLING = {
    "temperature",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
    "logprobs",
    "top_logprobs",
}


def base_model(model: str) -> str:
    return model.removeprefix("ft:").split(":", 1)[0] if model.startswith("ft:") else model


def _content(content):
    if isinstance(content, str) or content is None:
        return content
    parts = []
    for item in content:
        if isinstance(item, TextPromptMessageContent):
            parts.append({"type": "input_text", "text": item.data})
        elif isinstance(item, ImagePromptMessageContent) and (item.url or item.base64_data):
            parts.append(
                {"type": "input_image", "image_url": item.data, "detail": item.detail.value}
            )
        elif isinstance(item, DocumentPromptMessageContent) and item.url:
            parts.append({"type": "input_file", "file_url": item.url})
        elif isinstance(item, DocumentPromptMessageContent) and item.base64_data:
            parts.append(
                {
                    "type": "input_file",
                    "filename": item.filename or "document.pdf",
                    "file_data": item.data,
                }
            )
        else:
            raise InvokeBadRequestError(f"Unsupported OpenAI Responses content: {item.type.value}")
    return parts


def _input(messages) -> list[dict]:
    result = []
    for message in messages:
        if isinstance(message, ToolPromptMessage):
            result.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": _content(message.content) or "",
                }
            )
            continue
        if isinstance(message, AssistantPromptMessage) and isinstance(message.opaque_body, dict):
            stored = message.opaque_body.get(OUTPUT_KEY)
            if (
                isinstance(stored, list)
                and stored
                and all(isinstance(item, dict) for item in stored)
            ):
                for item in stored:
                    _wire.reject_controls(item, nested=False)
                result.extend(stored)
                continue
        if content := _content(message.content):
            result.append({"type": "message", "role": message.role.value, "content": content})
        if isinstance(message, AssistantPromptMessage):
            result.extend(
                {
                    "type": "function_call",
                    "call_id": call.id,
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                }
                for call in message.tool_calls
            )
    return result


def _payload(model, messages, parameters, tools, user, stream) -> dict:
    parameters = {k: v for k, v in parameters.items() if k in FIELDS}
    base = base_model(model)
    for alias in ("max_tokens", "max_completion_tokens"):
        if (value := parameters.pop(alias, None)) is not None:
            parameters.setdefault("max_output_tokens", value)
    parameters.pop("enable_stream", None)
    reasoning = {
        name: value
        for name in ("effort", "summary", "mode", "context")
        if (value := parameters.pop(f"reasoning_{name}", None)) not in (None, "")
    }
    if reasoning:
        parameters["reasoning"] = reasoning
    if base in {"gpt-6-astra", "gpt-6.1-sol"} and reasoning.get("effort") == "none":
        raise InvokeBadRequestError("The selected OpenAI model requires reasoning")
    if base.startswith(("gpt-6-", "gpt-6.1-")) and reasoning.get("effort") != "none":
        for name in SAMPLING:
            parameters.pop(name, None)
    for name in ("frequency_penalty", "presence_penalty"):
        if parameters.pop(name, None) not in (None, 0):
            raise InvokeBadRequestError(f"{name} requires Chat Completions")
    text = {}
    if (output_format := _wire.structured_format(parameters)) and output_format["type"] != "text":
        text["format"] = (
            {"type": "json_schema", **output_format["json_schema"]}
            if (output_format["type"] == "json_schema")
            else output_format
        )
    if (verbosity := parameters.pop("verbosity", None)) is not None:
        text["verbosity"] = verbosity
    if text:
        parameters["text"] = text
    if tools:
        parameters["tools"] = [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "strict": False,
            }
            for tool in tools
        ]
        if isinstance(choice := parameters.setdefault("tool_choice", "auto"), dict):
            name = (choice.get("function") or {}).get("name", choice.get("name"))
            if choice.get("type") != "function" or not isinstance(name, str) or not name:
                raise InvokeBadRequestError("Invalid OpenAI tool_choice")
            parameters["tool_choice"] = {"type": "function", "name": name}
    else:
        parameters.pop("tool_choice", None)
    if parameters.pop("logprobs", False) or "top_logprobs" in parameters:
        parameters.setdefault("include", []).append("message.output_text.logprobs")
    if user:
        digest = sha256(user.encode()).hexdigest()
        parameters.update(safety_identifier=digest, prompt_cache_key=digest)
    if (
        base.startswith(("gpt-5", "gpt-6"))
        and not base.endswith("-chat-latest")
        or len(base) > 1
        and base[0] == "o"
        and base[1].isdigit()
    ):
        parameters.setdefault("include", []).append("reasoning.encrypted_content")
    return {
        **parameters,
        "model": model,
        "input": _input(messages),
        "store": False,
        "stream": stream,
    }


def _valid_call(item: dict) -> bool:
    return (
        item.get("status") in (None, "completed")
        and isinstance(item.get("call_id"), str)
        and bool(item["call_id"])
        and isinstance(item.get("name"), str)
        and bool(item["name"])
        and isinstance(item.get("arguments"), str)
        and _wire.is_object(item["arguments"])
    )


def _terminal(payload, fallbacks: dict[int, dict] | None = None):
    status = payload.get("status")
    if payload.get("error") is not None or status == "failed":
        _wire.response_error(payload.get("error"))
    if status not in {"completed", "incomplete"}:
        raise InvokeServerUnavailableError("Tokener.ai returned an invalid Responses status")
    reason = {"max_output_tokens": "length", "content_filter": "content_filter"}.get(
        (payload.get("incomplete_details") or {}).get("reason"),
        "incomplete" if status == "incomplete" else "stop",
    )
    output = payload.get("output") or []
    if not output and fallbacks:
        output = [item for _, item in sorted(fallbacks.items())]
    committed = []
    visible = []
    size = 0
    thinking_spans = []
    calls = []
    for item in output:
        part = ""
        match item.get("type"):
            case "reasoning":
                part = "".join(block.get("text", "") for block in item.get("summary") or [])
                if part:
                    part = THINK_START + part + THINK_END
                    thinking_spans.append((size + len(THINK_START), size + len(part)))
            case "message":
                part = "".join(
                    block.get("text") or block.get("refusal") or ""
                    for block in item.get("content") or []
                )
            case "function_call":
                if status != "completed" or not _valid_call(item):
                    continue
                calls.append(_wire.tool_call(item["call_id"], item["name"], item["arguments"]))
        if part:
            visible.append(part)
            size += len(part)
        committed.append(item)
    return (
        "".join(visible) or payload.get("output_text", ""),
        calls,
        committed,
        "tool_calls" if calls else reason,
        thinking_spans,
    )


def _usage(llm, model, credentials, messages, tools, payload, output, calls):
    values = payload.get("usage") or {}
    proposed = [values.get("input_tokens"), values.get("output_tokens")]
    if any(type(value) is not int or value < 0 for value in proposed):
        proposed = [
            proposed[0]
            if type(proposed[0]) is int and proposed[0] >= 0
            else llm.get_num_tokens(model, credentials, messages, tools),
            proposed[1]
            if type(proposed[1]) is int and proposed[1] >= 0
            else count_text(model, output + "".join(call.function.arguments for call in calls)),
        ]
    return llm._calc_response_usage(model, credentials, *proposed)


def count_text(model: str, value: str) -> int:
    import tiktoken

    try:
        try:
            encoding = tiktoken.encoding_for_model(base_model(model))
        except KeyError:
            encoding = tiktoken.get_encoding("o200k_base")
        return len(encoding.encode(value, disallowed_special=()))
    except OSError:
        return (len(value.encode()) + 3) // 4


def count_messages(model, messages, tools) -> int:
    parts = []
    for message in messages:
        text = (
            message.content
            if isinstance(message.content, str)
            else "".join(
                item.data
                for item in message.content or []
                if isinstance(item, TextPromptMessageContent)
            )
        )
        parts.extend((message.role.value, message.name or "", text))
        if isinstance(message, AssistantPromptMessage):
            for call in message.tool_calls:
                parts.extend((call.id, call.function.name, call.function.arguments))
    if tools:
        parts.append(
            json.dumps(
                [tool.model_dump(mode="json") for tool in tools],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
    return count_text(model, "\n".join(parts)) + 3 * len(messages) + 3


def _stream(response, model, buffer: "StopBuffer") -> Generator:
    terminal = None
    completed_items = {}
    formatted = ""
    thinking_start = None
    thinking_spans = []
    for event_type, event in _sse.events(response):
        if event_type in {"error", "response.failed", "response.cancelled"}:
            _wire.response_error(event.get("response", {}).get("error") or event)
        if event_type in {"response.completed", "response.incomplete"}:
            terminal = event.get("response")
            break
        if event_type == "response.output_item.done":
            completed_items[event.get("output_index", 0)] = event["item"]
        if event_type not in {
            "response.reasoning_summary_text.delta",
            "response.output_text.delta",
            "response.refusal.delta",
        }:
            continue
        part = event.get("delta", "")
        if not part:
            continue
        is_thinking = event_type == "response.reasoning_summary_text.delta"
        if is_thinking and thinking_start is None:
            thinking_start = len(formatted) + len(THINK_START)
            part = THINK_START + part
        elif not is_thinking and thinking_start is not None:
            thinking_spans.append((thinking_start, len(formatted) + len(THINK_END)))
            thinking_start = None
            part = THINK_END + part
        formatted += part
        if visible := buffer.push(part):
            yield _wire.chunk(model, visible)
    if not isinstance(terminal, dict):
        raise InvokeConnectionError("Tokener.ai Responses stream ended without a terminal event")
    canonical, calls, output, finish, canonical_spans = _terminal(terminal, completed_items)
    if canonical.startswith(formatted):
        if thinking_start is not None:
            active_span = next(
                (span for span in canonical_spans if span[0] == thinking_start),
                (thinking_start, len(formatted) + len(THINK_END)),
            )
            thinking_spans.append(active_span)
        thinking_spans.extend(span for span in canonical_spans if span[0] >= len(formatted))
        if visible := buffer.push(canonical[len(formatted) :]):
            yield _wire.chunk(model, visible)
        formatted = canonical
    elif thinking_start is not None:
        formatted += THINK_END
        thinking_spans.append((thinking_start, len(formatted)))
        if visible := buffer.push(THINK_END):
            yield _wire.chunk(model, visible)
    if closing := buffer.close_thinking(thinking_spans):
        yield _wire.chunk(model, closing)
    if visible := buffer.finish():
        yield _wire.chunk(model, visible)
    return terminal, canonical or formatted, calls, output, finish


def invoke(llm, model, credentials, messages, parameters, tools, stop, stream, user) -> Generator:
    stream = (
        stream
        and parameters.get("enable_stream") is not False
        and base_model(model) not in NON_STREAMING
    )
    payload = _payload(model, messages, parameters, tools, user, stream)
    buffer = StopBuffer(stop)
    with llm._request("responses", credentials, json=payload, stream=stream) as response:
        if stream:
            result, raw, calls, output, finish = yield from _stream(response, model, buffer)
            content = ""
        else:
            result = response.json()
            if not isinstance(result, dict):
                raise InvokeServerUnavailableError(
                    "Tokener.ai returned an invalid Responses object"
                )
            raw, calls, output, finish, thinking_spans = _terminal(result)
            content = buffer.push(raw) + buffer.finish() + buffer.close_thinking(thinking_spans)
        if buffer.stopped:
            calls, output, finish = [], [], "stop"
        yield _wire.chunk(
            result.get("model", model),
            content,
            calls=calls,
            finish=finish,
            opaque={OUTPUT_KEY: output} if not buffer.stopped else None,
            usage=_usage(llm, model, credentials, messages, tools, result, raw, calls),
        )


class StopBuffer:
    def __init__(self, stop: list[str] | None) -> None:
        self.tokens = [token for token in stop or [] if token]
        self.keep = max((len(token) for token in self.tokens), default=1) - 1
        self.pending = ""
        self.emitted = 0
        self.cut_at: int | None = None

    @property
    def stopped(self) -> bool:
        return self.cut_at is not None

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
            self.cut_at = self.emitted + len(result)
            return result
        emit = len(self.pending) - self.keep
        if emit <= 0:
            return ""
        result, self.pending = self.pending[:emit], self.pending[emit:]
        self.emitted += len(result)
        return result

    def close_thinking(self, spans: list[tuple[int, int]]) -> str:
        if self.cut_at is None or any(token in THINK_END for token in self.tokens):
            return ""
        return THINK_END if any(start <= self.cut_at < end for start, end in spans) else ""

    def finish(self) -> str:
        if self.stopped:
            return ""
        result, self.pending = self.pending, ""
        return result
