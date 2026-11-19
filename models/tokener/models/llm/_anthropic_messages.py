import re
from collections.abc import Generator
from copy import deepcopy

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
    InvokeError,
    InvokeServerUnavailableError,
)

from models.llm import _sse, _wire

CACHE_FLAGS = {
    "prompt_caching_tool_definitions",
    "prompt_caching_system_message",
    "prompt_caching_images",
    "prompt_caching_documents",
    "prompt_caching_tool_results",
    "prompt_caching_message_flow",
    "prompt_caching_ttl",
}
FIELDS = CACHE_FLAGS | {
    "thinking",
    "thinking_budget",
    "thinking_display",
    "effort",
    "reasoning_effort",
    "task_budget",
    "context_1m",
    "extended_output",
    "max_tokens",
    "max_tokens_to_sample",
    "temperature",
    "top_p",
    "top_k",
    "json_schema",
    "response_format",
    "tool_choice",
    "stop_sequences",
}
ADAPTIVE = (
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-5",
    "claude-fable-5",
    "claude-mythos-5",
)
ALWAYS_ADAPTIVE = ("claude-opus-5-5", "claude-fable-5", "claude-mythos-5")
DEFAULT_ADAPTIVE = ("claude-sonnet-5", "claude-opus-5", "claude-haiku-5")
OPAQUE_KEY = "anthropic_thinking"


class CacheBlocks:
    def __init__(self, settings: dict) -> None:
        self.settings = settings
        self.blocks: list[tuple[int, int, dict]] = []

    def mark(self, block: dict, priority: int, length: int = 0) -> None:
        self.blocks.append((priority, -length, block))

    def apply(self) -> None:
        control = {"type": "ephemeral"}
        if (ttl := self.settings.get("prompt_caching_ttl")) is not None:
            if ttl not in ("5m", "1h"):
                raise InvokeBadRequestError("prompt_caching_ttl must be 5m or 1h")
            control["ttl"] = ttl
        for _, _, block in sorted(self.blocks, key=lambda item: item[:2])[:4]:
            block["cache_control"] = control

    def system(self, value: str) -> list[dict]:
        enabled = self.settings.get("prompt_caching_system_message", False)
        parts = re.split(r"(</?cache\s*>)", value, flags=re.IGNORECASE)
        if not enabled:
            text = "".join(parts[::2])
            return [{"type": "text", "text": text}] if text else []
        blocks = []
        marked = False
        for i, text in enumerate(parts):
            if i % 2:
                marked = not text.startswith("</")
            elif text:
                block = {"type": "text", "text": text}
                blocks.append(block)
                if marked:
                    self.mark(block, 2, len(text))
        return blocks

    def content(self, value) -> list[dict]:
        if isinstance(value, str):
            value = [TextPromptMessageContent(data=value)] if value else []
        blocks = []
        for item in value or []:
            if isinstance(item, TextPromptMessageContent):
                if not item.data:
                    continue
                block = {"type": "text", "text": item.data}
                if (threshold := self.settings.get("prompt_caching_message_flow", 0)) and (
                    len(item.data.split()) >= threshold
                ):
                    self.mark(block, 3, len(item.data))
            elif isinstance(item, ImagePromptMessageContent | DocumentPromptMessageContent):
                kind = item.type.value
                if kind == "document" and item.mime_type != "application/pdf":
                    raise InvokeBadRequestError("Anthropic documents must be PDFs")
                if item.url:
                    source = {"type": "url", "url": item.url}
                elif item.base64_data:
                    source = {
                        "type": "base64",
                        "media_type": item.mime_type,
                        "data": item.base64_data,
                    }
                else:
                    raise InvokeBadRequestError("Anthropic attachment has no data")
                block = {"type": kind, "source": source}
                if self.settings.get(f"prompt_caching_{kind}s"):
                    self.mark(block, 1, len(item.base64_data))
            else:
                raise InvokeBadRequestError(f"Unsupported Anthropic content: {item.type.value}")
            blocks.append(block)
        return blocks


def _history(messages, cache: CacheBlocks) -> tuple[list, list]:
    system_parts, turns = [], []
    for message in messages:
        if message.role.value in {"system", "developer"}:
            values = (
                [message.content]
                if isinstance(message.content, str)
                else [
                    item.data
                    for item in message.content or []
                    if isinstance(item, TextPromptMessageContent)
                ]
            )
            system_parts.extend(value.strip() for value in values)
    system = cache.system("\n".join(system_parts))
    for message in messages:
        if message.role.value in {"system", "developer"}:
            continue
        role = "user"
        if isinstance(message, AssistantPromptMessage):
            role = "assistant"
            stored = (
                (message.opaque_body or {}).get(OPAQUE_KEY, [])
                if isinstance(message.opaque_body, dict)
                else []
            )
            blocks = [
                item
                for item in stored
                if isinstance(item, dict)
                and item.get("type")
                in {
                    "thinking",
                    "redacted_thinking",
                }
            ]
            for block in blocks:
                _wire.reject_controls(block, nested=False)
            text = (
                _wire.without_thinking(message.content)
                if isinstance(message.content, str)
                else message.content
            )
            blocks.extend(cache.content(text))
            for call in message.tool_calls:
                block = {
                    "type": "tool_use",
                    "id": call.id,
                    "name": call.function.name,
                    "input": _wire.json_object(call.function.arguments, "Tool arguments"),
                }
                if cache.settings.get("prompt_caching_tool_results"):
                    cache.mark(block, 4)
                blocks.append(block)
        elif isinstance(message, ToolPromptMessage):
            block = {
                "type": "tool_result",
                "tool_use_id": message.tool_call_id,
                "content": cache.content(message.content),
            }
            if cache.settings.get("prompt_caching_tool_results"):
                cache.mark(block, 4)
            blocks = [block]
        else:
            blocks = cache.content(message.content)
        if not blocks:
            continue
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"].extend(blocks)
        else:
            turns.append({"role": role, "content": blocks})
    return system, turns


def _tool_choice(choice) -> dict:
    if isinstance(choice, dict):
        name = (choice.get("function") or {}).get("name", choice.get("name"))
        if choice.get("type") in ("tool", "function") and name:
            return {"type": "tool", "name": name}
        choice = choice.get("type")
    if choice in ("auto", "none", "any", "required"):
        return {"type": "any" if choice == "required" else choice}
    raise InvokeBadRequestError("Invalid Anthropic tool_choice")


def _payload(model, messages, parameters, tools, stop, *, stream=False, count=False):
    settings = {key: value for key, value in parameters.items() if key in CACHE_FLAGS}
    cache = CacheBlocks(settings)
    system, turns = _history(messages, cache)
    payload = {"model": model, "messages": turns}
    if system:
        payload["system"] = system
    if tools:
        definitions = []
        for tool in tools:
            schema = deepcopy(tool.parameters)
            for prop in schema.get("properties", {}).values():
                if prop.get("type") == "select":
                    prop["type"] = "string"
                    if "enum" not in prop:
                        prop["enum"] = (
                            [item["value"] for item in prop["options"] if "value" in item]
                            if "options" in prop
                            else [prop.get("default", "")]
                        )
            definitions.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": schema,
                }
            )
        if settings.get("prompt_caching_tool_definitions"):
            for definition in definitions:
                cache.mark(definition, 4)
        payload["tools"] = definitions
    cache.apply()
    adaptive = model.startswith(ADAPTIVE)
    if count:
        payload["messages"] = turns or [{"role": "user", "content": "Hello"}]
        if any(
            block.get("type") in {"thinking", "redacted_thinking"}
            for turn in turns
            for block in turn["content"]
        ):
            payload["thinking"] = (
                {"type": "adaptive"} if adaptive else {"type": "enabled", "budget_tokens": 4096}
            )
        return payload, {"anthropic-version": "2026-10-21"}

    params = {key: value for key, value in parameters.items() if key in FIELDS - CACHE_FLAGS}
    raw_schema = params.get("json_schema")
    if isinstance(raw_schema, str) and not raw_schema.strip():
        params.pop("json_schema")
    elif raw_schema is not None:
        schema = _wire.json_object(raw_schema, "json_schema")
        if set(schema) == {"schema", "name"} and schema["name"] == "llm_response":
            schema = schema["schema"]
        if not isinstance(schema, dict) or not schema:
            raise InvokeBadRequestError("json_schema must be a non-empty object")
        params["json_schema"] = {"schema": schema}
    output_format = _wire.structured_format(params)
    thinking = params.pop("thinking", None)
    display = params.pop("thinking_display", "omitted" if adaptive else "summarized")
    budget = params.pop("thinking_budget", 1024)
    effort = params.pop("effort", params.pop("reasoning_effort", None))
    if isinstance(thinking, dict):
        display = thinking.get("display", display)
        budget = thinking.get("budget_tokens", budget)
        thinking = thinking.get("type") in {"enabled", "adaptive"}
    if model.startswith(ALWAYS_ADAPTIVE) or (adaptive and thinking):
        payload["thinking"] = {"type": "adaptive", "display": display}
    elif adaptive and thinking is False and model.startswith(DEFAULT_ADAPTIVE):
        payload["thinking"] = {
            "type": "between_tools" if model.startswith("claude-sonnet-5-5") else "disabled"
        }
        if effort in {"xhigh", "max"} and model.startswith(
            ("claude-opus-5", "claude-haiku-5", "claude-sonnet-5-5")
        ):
            effort = "high"
    elif not adaptive and thinking:
        payload["thinking"] = {"type": "enabled", "budget_tokens": budget}

    output = {}
    betas = []
    if effort:
        output["effort"] = effort
    if (task_budget := params.get("task_budget")) and task_budget >= 20000 and adaptive:
        output["task_budget"] = {"type": "tokens", "total": task_budget}
        betas.append("task-budgets-2026-03-13")
    if output_format and output_format["type"] == "json_schema":
        output["format"] = {"type": "json_schema", "schema": output_format["json_schema"]["schema"]}
    elif output_format and output_format["type"] == "json_object":
        payload.setdefault("system", []).append(
            {
                "type": "text",
                "text": "Return only a valid JSON object without Markdown or code fences.",
            }
        )
    if output:
        payload["output_config"] = output
    if params.get("context_1m") and not adaptive:
        betas.append("context-1m-2025-08-07")
    if params.get("extended_output"):
        betas.append("output-128k-2025-02-19")
    sampling = (
        {name: params[name] for name in ("temperature", "top_p", "top_k") if name in params}
        if not (adaptive or thinking or output)
        else {}
    )
    headers = {"anthropic-version": "2023-06-01" if sampling else "2026-10-21"}
    if betas:
        headers["anthropic-beta"] = ",".join(betas)
    payload.update(
        sampling,
        max_tokens=params.get("max_tokens_to_sample", params.get("max_tokens", 4096)),
        stream=stream,
    )
    if stop := stop or params.get("stop_sequences"):
        payload["stop_sequences"] = stop
    if tools and (choice := params.get("tool_choice")) is not None:
        payload["tool_choice"] = _tool_choice(choice)
    return payload, headers


def _stream(response, model):
    usage, blocks, arguments = {}, {}, {}
    reason, started, stopped = None, False, False
    thinking = False
    for event_type, event in _sse.events(response):
        if event_type == "error" or "error" in event:
            _wire.response_error(event.get("error"))
        match event_type:
            case "message_start":
                started = True
                usage.update(event["message"].get("usage") or {})
            case "content_block_start":
                block = blocks[event["index"]] = event["content_block"].copy()
                if block["type"] == "thinking" and block.get("thinking"):
                    thinking = True
                    yield _wire.chunk(model, "<think>\n" + block.get("thinking", ""))
                elif block["type"] == "text" and block.get("text"):
                    yield _wire.chunk(model, block["text"])
            case "content_block_delta":
                index = event["index"]
                delta = event["delta"]
                block = blocks[index]
                if delta["type"] == "input_json_delta":
                    arguments[index] = arguments.get(index, "") + delta["partial_json"]
                else:
                    field = {
                        "thinking_delta": "thinking",
                        "signature_delta": "signature",
                        "text_delta": "text",
                    }.get(delta["type"])
                    if field:
                        block[field] = block.get(field, "") + delta[field]
                        if field != "signature" and delta[field]:
                            if field == "thinking" and not thinking:
                                thinking = True
                                yield _wire.chunk(model, "<think>\n")
                            yield _wire.chunk(model, delta[field])
            case "content_block_stop":
                index = event["index"]
                if thinking and blocks[index]["type"] == "thinking":
                    thinking = False
                    yield _wire.chunk(model, "\n</think>\n\n")
                if index in arguments:
                    raw = arguments.pop(index)
                    blocks[index]["input"] = (
                        _wire.json_object(raw, "Tool arguments") if _wire.is_object(raw) else None
                    )
            case "message_delta":
                reason = event["delta"].get("stop_reason") or reason
                usage.update(event.get("usage") or {})
            case "message_stop":
                stopped = True
                break
    if not started or not stopped:
        raise InvokeConnectionError("Tokener.ai Messages stream ended without a terminal event")
    return [block for _, block in sorted(blocks.items())], usage, reason


def _result(blocks, *, discard_calls: bool = False):
    content, calls, thinking = [], [], []
    for block in blocks:
        match block.get("type"):
            case "thinking":
                if block.get("signature"):
                    thinking.append({key: block[key] for key in ("type", "thinking", "signature")})
            case "redacted_thinking":
                if block.get("data"):
                    thinking.append({"type": "redacted_thinking", "data": block["data"]})
            case "text":
                content.append(block.get("text", ""))
            case "tool_use":
                if not discard_calls and isinstance(block.get("input"), dict):
                    calls.append(_wire.tool_call(block["id"], block["name"], block["input"]))
    return "".join(content), calls, {OPAQUE_KEY: thinking} if thinking else None


def _prompt_tokens(model, usage, parameters):
    creation = usage.get("cache_creation") or {}
    short = creation.get("ephemeral_5m_input_tokens") or 0
    long = creation.get("ephemeral_1h_input_tokens") or 0
    writes = (
        short * 5 // 4 + long * 2
        if short or long
        else (usage.get("cache_creation_input_tokens") or 0)
        * (8 if parameters.get("prompt_caching_ttl") == "1h" else 5)
        // 4
    )
    divisor = (
        40
        if model == "claude-fable-5-1"
        else (20 if model in {"claude-opus-5-5", "claude-sonnet-5-5"} else 10)
    )
    return (
        (usage.get("input_tokens") or 0)
        + writes
        + (usage.get("cache_read_input_tokens") or 0) // divisor
    )


def invoke(llm, model, credentials, messages, parameters, tools, stop, stream) -> Generator:
    payload, headers = _payload(model, messages, parameters, tools, stop, stream=stream)
    with llm._request(
        "messages", credentials, json=payload, headers=headers, stream=stream
    ) as response:
        if stream:
            blocks, usage, reason = yield from _stream(response, model)
        else:
            result = response.json()
            if not isinstance(result, dict) or not isinstance(result.get("content"), list):
                raise InvokeServerUnavailableError(
                    "Tokener.ai returned an invalid Messages response"
                )
            blocks, usage, reason = (
                result["content"],
                result.get("usage") or {},
                result.get("stop_reason"),
            )
        content, calls, opaque = _result(blocks, discard_calls=reason == "max_tokens")
        finish = {
            "max_tokens": "length",
            "end_turn": "stop",
            "stop_sequence": "stop",
            "tool_use": "tool_calls",
        }.get(reason, reason)
        yield _wire.chunk(
            model,
            "" if stream else content,
            calls=calls,
            opaque=opaque,
            finish=finish,
            usage=llm._calc_response_usage(
                model,
                credentials,
                _prompt_tokens(model, usage, parameters),
                usage.get("output_tokens") or 0,
            ),
        )


def count_tokens(llm, model, credentials, messages, tools) -> int | None:
    payload, headers = _payload(model, messages, {}, tools, None, count=True)
    try:
        with llm._request(
            "messages/count_tokens", credentials, json=payload, headers=headers
        ) as response:
            result = response.json()
    except InvokeBadRequestError:
        raise
    except InvokeError:
        return None
    count = result.get("input_tokens") if isinstance(result, dict) else None
    return count if type(count) is int and count >= 0 else None
