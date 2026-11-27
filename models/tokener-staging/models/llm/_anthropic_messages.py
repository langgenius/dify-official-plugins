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
    InvokeError,
    InvokeServerUnavailableError,
)

from models.llm import _anthropic_format, _wire
from models.llm._anthropic_stream import (
    OPAQUE_KEY as OPAQUE_KEY,
)
from models.llm._anthropic_stream import (
    _result as _result,
)
from models.llm._anthropic_stream import (
    _stream as _stream,
)

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
    "speed",
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
NO_PREFILL = (
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    *ADAPTIVE,
)
ALWAYS_ADAPTIVE = ("claude-opus-5-5", "claude-fable-5", "claude-mythos-5")
DEFAULT_ADAPTIVE = ("claude-sonnet-5", "claude-opus-5", "claude-haiku-5")


class CacheBlocks:
    def __init__(self, settings: dict) -> None:
        self.settings = settings
        self.blocks: list[tuple[int, int, dict]] = []

    def mark(self, block: dict, priority: int, length: int = 0) -> None:
        self.blocks.append((priority, -length, block))

    def text(self, block: dict) -> dict:
        threshold = self.settings.get("prompt_caching_message_flow", 0)
        if threshold and len(block["text"].split()) >= threshold:
            self.mark(block, 3, len(block["text"]))
        return block

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
                block = self.text({"type": "text", "text": item.data})
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
            opaque = message.opaque_body if isinstance(message.opaque_body, dict) else {}
            if OPAQUE_KEY not in opaque and isinstance(opaque.get("anthropic_content"), list):
                blocks = []
                tool_ids = set()
                for item in opaque["anthropic_content"]:
                    if not isinstance(item, dict):
                        continue
                    kind = item.get("type")
                    _wire.reject_controls(
                        {
                            k: v
                            for k, v in item.items()
                            if not (kind == "tool_use" and k == "input")
                        },
                        nested=False,
                    )
                    if kind == "thinking" and item.get("signature"):
                        blocks.append(deepcopy(item))
                    elif kind == "redacted_thinking" and item.get("data"):
                        blocks.append({"type": "redacted_thinking", "data": item["data"]})
                    elif kind == "text" and isinstance(item.get("text"), str) and item["text"]:
                        blocks.append(cache.text(deepcopy(item)))
                    elif kind == "tool_use" and item.get("id") and item.get("name"):
                        block = {
                            "type": "tool_use",
                            "id": item["id"],
                            "name": item["name"],
                            "input": item.get("input")
                            if isinstance(item.get("input"), dict)
                            else {},
                        }
                        if cache.settings.get("prompt_caching_tool_results"):
                            cache.mark(block, 4)
                        blocks.append(block)
                        tool_ids.add(block["id"])
                for call in message.tool_calls:
                    if call.id in tool_ids:
                        continue
                    block = {
                        "type": "tool_use",
                        "id": call.id,
                        "name": call.function.name,
                        "input": _wire.json_object(call.function.arguments, "Tool arguments"),
                    }
                    if cache.settings.get("prompt_caching_tool_results"):
                        cache.mark(block, 4)
                    blocks.append(block)
            else:
                stored = opaque.get(OPAQUE_KEY, [])
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
    if (task_budget := params.pop("task_budget", None)) is not None and (
        type(task_budget) is not int or task_budget < 0
    ):
        raise InvokeBadRequestError("Invalid Anthropic task_budget")
    if (speed := params.pop("speed", None)) is not None and speed not in ("standard", "fast"):
        raise InvokeBadRequestError("Invalid Anthropic speed")
    if (
        task_budget is not None
        and task_budget >= 20000
        and model.startswith(ADAPTIVE)
        and not model.startswith("claude-sonnet-5")
    ):
        output["task_budget"] = {"type": "tokens", "total": task_budget}
        betas.append("task-budgets-2026-03-13")
    if speed is not None:
        payload["speed"] = speed
    if effort:
        output["effort"] = effort
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
    max_tokens = params.get("max_tokens_to_sample", params.get("max_tokens", 4096))
    if model == "claude-3-5-sonnet-20240620" and max_tokens > 4096:
        betas.append("max-tokens-3-5-sonnet-2024-07-15")
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
        max_tokens=max_tokens,
        stream=stream,
    )
    if stop := stop or params.get("stop_sequences"):
        payload["stop_sequences"] = stop
    if tools and (choice := params.get("tool_choice")) is not None:
        payload["tool_choice"] = _tool_choice(choice)
    return payload, headers


def invoke(llm, model, credentials, messages, parameters, tools, stop, stream) -> Generator:
    payload, headers = _payload(model, messages, parameters, tools, stop, stream=stream)
    with llm._request(
        "messages", credentials, json=payload, headers=headers, stream=stream
    ) as response:
        if stream:
            blocks, usage, reason, stop_details = yield from _stream(response, model)
        else:
            result = response.json()
            if not isinstance(result, dict) or not isinstance(result.get("content"), list):
                raise InvokeServerUnavailableError(
                    "Tokener.ai returned an invalid Messages response"
                )
            blocks, usage, reason, stop_details = (
                result["content"],
                result.get("usage") or {},
                result.get("stop_reason"),
                result.get("stop_details"),
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
            usage=_anthropic_format.priced_usage(
                llm,
                model,
                credentials,
                usage,
                parameters,
                reason=reason,
                stop_details=stop_details,
                has_content=bool(blocks),
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
