import base64
import re
from collections.abc import Generator

from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    TextPromptMessageContent,
    ToolPromptMessage,
)
from dify_plugin.errors.model import (
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeServerUnavailableError,
)

from models.llm import _gemini_files, _sse, _wire

FIELDS = {
    "max_tokens",
    "max_output_tokens",
    "temperature",
    "top_p",
    "top_k",
    "json_schema",
    "response_format",
    "thinking_mode",
    "thinking_budget",
    "thinking_level",
    "include_thoughts",
    "reasoning_effort",
    "media_resolution",
    "use_inline_file",
    "grounding",
    "url_context",
    "code_execution",
    "resolution",
    "aspect_ratio",
    "service_tier",
    "flex_inference",
    "tool_choice",
}
NATIVE_TOOLS = {
    "grounding": ("googleSearch", "google_search"),
    "url_context": ("urlContext", "url_context"),
    "code_execution": ("codeExecution", "code_execution"),
}
OPAQUE_KEY = "gemini_parts"


def model_path(model: str, operation: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", model):
        raise InvokeBadRequestError("Invalid Gemini model ID")
    return f"/v1beta/models/{model}:{operation}"


def _parts(llm, credentials, value, *, inline: bool) -> list[dict]:
    if isinstance(value, str):
        return [{"text": value}] if value else []
    parts = []
    for item in value or []:
        if isinstance(item, TextPromptMessageContent):
            if item.data:
                parts.append({"text": item.data})
            continue
        mime = item.mime_type
        if item.type.value == "document" and mime != "application/pdf":
            raise InvokeBadRequestError("Gemini requires PDF documents")
        if not mime.startswith(("image/", "audio/", "video/")) and mime != "application/pdf":
            raise InvokeBadRequestError("Unsupported Gemini attachment type")
        data = _gemini_files.media_bytes(item)
        if inline or mime.startswith("image/"):
            parts.append(
                {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}}
            )
        else:
            uri = _gemini_files.upload(llm, credentials, mime, data)
            parts.append({"fileData": {"mimeType": mime, "fileUri": uri}})
    return parts


def _history(llm, credentials, messages, *, inline) -> tuple[str, list]:
    system, contents = [], []
    names = {}
    for message in messages:
        if message.role.value in {"system", "developer"}:
            system.append(message.get_text_content())
            continue
        role = "model" if isinstance(message, AssistantPromptMessage) else "user"
        if isinstance(message, ToolPromptMessage):
            output = message.get_text_content()
            try:
                result = _wire.json_object(output, "Tool result")
            except InvokeBadRequestError:
                result = {"result": output}
            name = names.get(message.tool_call_id) or message.name or message.tool_call_id
            parts = [{"functionResponse": {"name": name, "response": result}}]
        elif isinstance(message, AssistantPromptMessage):
            stored = (
                message.opaque_body.get(OPAQUE_KEY, [])
                if isinstance(message.opaque_body, dict)
                else []
            )
            for call in message.tool_calls:
                names[call.id] = call.function.name
            if stored:
                if not isinstance(stored, list) or not all(
                    isinstance(part, dict) for part in stored
                ):
                    raise InvokeBadRequestError("Invalid Gemini assistant history")
                for part in stored:
                    _wire.reject_controls(part, nested=False)
                parts = stored
            else:
                text = (
                    _wire.without_thinking(message.content)
                    if isinstance(message.content, str)
                    else message.content
                )
                parts = _parts(llm, credentials, text, inline=inline)
                parts.extend(
                    {
                        "functionCall": {
                            "name": call.function.name,
                            "args": _wire.json_object(call.function.arguments, "Tool arguments"),
                        },
                    }
                    for call in message.tool_calls
                )
        else:
            parts = _parts(llm, credentials, message.content, inline=inline)
        if not parts:
            continue
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": role, "parts": list(parts)})
    return "\n".join(system), contents


def _tool_config(choice) -> dict:
    if isinstance(choice, dict):
        name = (choice.get("function") or {}).get("name", choice.get("name"))
        if not name:
            raise InvokeBadRequestError("Invalid Gemini tool_choice")
        return {"mode": "ANY", "allowedFunctionNames": [name]}
    mode = {"auto": "AUTO", "required": "ANY", "any": "ANY", "none": "NONE"}.get(choice)
    if mode is None:
        raise InvokeBadRequestError("Invalid Gemini tool_choice")
    return {"mode": mode}


def _interaction_step(turn, resolution):
    content = []
    for part in turn["parts"]:
        if "text" in part and not part.get("thought"):
            content.append({"type": "text", "text": part["text"]})
        elif media := part.get("inlineData") or part.get("fileData"):
            mime = media["mimeType"]
            kind = "document" if mime == "application/pdf" else mime.split("/", 1)[0]
            item = {"type": kind, "mime_type": mime}
            if "data" in media:
                item["data"] = media["data"]
            else:
                item["uri"] = media["fileUri"]
            if resolution in {"low", "medium", "high"} and kind in {"image", "video"}:
                item["resolution"] = resolution
            content.append(item)
        elif "functionCall" in part or "functionResponse" in part:
            raise InvokeBadRequestError(
                "Gemini Interactions cannot replay GenerateContent function history"
            )
    return {"type": "model_output" if turn["role"] == "model" else "user_input", "content": content}


def _request(llm, model, credentials, messages, params, tools, stop, stream):
    response_format = _wire.structured_format(params.copy())
    schema = (response_format or {}).get("json_schema", {}).get("schema")
    native_tools = [pair for name, pair in NATIVE_TOOLS.items() if params.get(name)]
    interactions = schema and native_tools and not tools and re.match(r"gemini-3(?:[.-]|$)", model)
    resolution = str(params.get("media_resolution", "")).lower()
    if (
        interactions
        and resolution in {"low", "medium", "high"}
        and any(
            item.type.value == "document"
            for message in messages
            for item in (message.content if isinstance(message.content, list) else [])
        )
    ):
        raise InvokeBadRequestError(
            "Gemini Interactions does not support media_resolution for PDFs"
        )
    system, contents = _history(
        llm, credentials, messages, inline=params.get("use_inline_file", False)
    )
    max_tokens = params.get("max_output_tokens", params.get("max_tokens"))
    tier = "flex" if params.get("flex_inference") else params.get("service_tier")
    level = params.get("thinking_level", params.get("reasoning_effort"))
    include_thoughts = params.get("include_thoughts")

    if interactions:
        config = {}
        if max_tokens is not None:
            config["max_output_tokens"] = max_tokens
        if stop:
            config["stop_sequences"] = stop
        if level:
            config["thinking_level"] = str(level).lower()
        if include_thoughts is not None:
            config["thinking_summaries"] = "auto" if include_thoughts else "none"
        if not contents and system:
            contents = [{"role": "user", "parts": [{"text": system}]}]
        steps = [_interaction_step(turn, resolution) for turn in contents]
        payload = {
            "model": model,
            "input": [step for step in steps if step["content"]],
            "store": False,
            "stream": stream,
            "tools": [{"type": name} for _, name in native_tools],
            "response_format": {"type": "text", "mime_type": "application/json", "schema": schema},
        }
        if config:
            payload["generation_config"] = config
        if system:
            payload["system_instruction"] = system
        if tier:
            payload["service_tier"] = tier.lower()
        return "/v1beta/interactions" + ("?alt=sse" if stream else ""), payload, True

    config = {
        wire: params[name]
        for name, wire in (
            ("temperature", "temperature"),
            ("top_p", "topP"),
            ("top_k", "topK"),
        )
        if name in params
    }
    if max_tokens is not None:
        config["maxOutputTokens"] = max_tokens
    if stop:
        config["stopSequences"] = stop
    if response_format and response_format["type"] != "text":
        config["responseMimeType"] = "application/json"
        if schema is not None:
            config["responseJsonSchema"] = schema
    if resolution in {"default", "low", "medium", "high"}:
        config["mediaResolution"] = "MEDIA_RESOLUTION_" + (
            "UNSPECIFIED" if resolution == "default" else resolution.upper()
        )
    if re.search(r"(?:^|-)image(?:-|$)", model):
        config["responseModalities"] = ["TEXT", "IMAGE"]
        image = {
            wire: params[name]
            for name, wire in (
                ("aspect_ratio", "aspectRatio"),
                ("resolution", "imageSize"),
            )
            if name in params
        }
        if image:
            config["imageConfig"] = image
    else:
        thinking = {}
        budget = params.get("thinking_budget")
        if params.get("thinking_mode") is False:
            budget = 0
        elif budget == 0 or (budget is None and params.get("thinking_mode")):
            budget = -1
        if budget is not None:
            thinking["thinkingBudget"] = budget
        if level:
            thinking["thinkingLevel"] = str(level).upper()
        if include_thoughts is not None:
            thinking["includeThoughts"] = include_thoughts
        if thinking:
            config["thinkingConfig"] = thinking
    payload = {"contents": contents}
    if config:
        payload["generationConfig"] = config
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    if tier:
        payload["serviceTier"] = tier.upper()
    native = [{name: {}} for name, _ in native_tools]
    if tools:
        native.append(
            {
                "functionDeclarations": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "parametersJsonSchema": tool.parameters,
                    }
                    for tool in tools
                ]
            }
        )
        if (choice := params.get("tool_choice")) is not None:
            payload["toolConfig"] = {"functionCallingConfig": _tool_config(choice)}
    if native:
        payload["tools"] = native
    path = model_path(model, "streamGenerateContent" if stream else "generateContent")
    return path + ("?alt=sse" if stream else ""), payload, False


class Output:
    def __init__(self) -> None:
        self.parts: list[dict] = []
        self.calls: list = []
        self.thinking = False

    def read(self, parts: list) -> list:
        visible = []
        for part in parts:
            self.parts.append(part)
            if "text" in part:
                text = part["text"]
                thought = bool(part.get("thought"))
                if thought != self.thinking:
                    text = ("<think>\n" if thought else "\n</think>\n") + text
                    self.thinking = thought
                if text:
                    visible.append(TextPromptMessageContent(data=text))
            if "inlineData" in part:
                if self.thinking:
                    visible.append(TextPromptMessageContent(data="\n</think>\n"))
                    self.thinking = False
                data = part["inlineData"]
                if data["mimeType"].startswith("image/"):
                    visible.append(
                        ImagePromptMessageContent(
                            format="." + data["mimeType"].split("/", 1)[1],
                            mime_type=data["mimeType"],
                            base64_data=data["data"],
                        )
                    )
            if call := part.get("functionCall"):
                name = call["name"]
                self.calls.append(
                    _wire.tool_call(
                        call.get("id") or f"gemini-{len(self.calls)}-{name}",
                        name,
                        call.get("args") or {},
                    )
                )
        return visible

    def close_thinking(self) -> list:
        return [TextPromptMessageContent(data="\n</think>\n")] if self.thinking else []


def _generate(llm, model, credentials, path, payload, stream) -> Generator:
    output = Output()
    visible = []
    tokens = [0, 0]
    seen = set()
    finish = None
    for _ in range(8):
        continuation = None
        usage = {}
        timeout = (10, 900 if model == "gemini-4-argon" else 120)
        with llm._request_at(
            path, credentials, json=payload, stream=stream, timeout=timeout
        ) as response:
            replies = (event for _, event in _sse.events(response)) if stream else [response.json()]
            for result in replies:
                if not isinstance(result, dict):
                    raise InvokeServerUnavailableError(
                        "Tokener.ai returned an invalid Gemini response"
                    )
                if result.get("error"):
                    _wire.response_error(result["error"])
                if result.get("usageMetadata"):
                    usage.update(result["usageMetadata"])
                if (
                    block := result.get("promptFeedback", {}).get("blockReason")
                ) and block != "BLOCK_REASON_UNSPECIFIED":
                    finish = "content_filter"
                candidates = result.get("candidates") or []
                if not candidates:
                    continue
                candidate = candidates[0]
                if parts := output.read((candidate.get("content") or {}).get("parts") or []):
                    if stream:
                        yield _wire.chunk(model, parts)
                    else:
                        visible.extend(parts)
                finish = candidate.get("finishReason") or finish
                continuation = candidate.get("continuationToken") or continuation
        tokens[0] += usage.get("promptTokenCount") or 0
        tokens[1] += (usage.get("candidatesTokenCount") or 0) + (
            usage.get("thoughtsTokenCount") or 0
        )
        if not continuation:
            if finish is None:
                raise InvokeConnectionError(
                    "Tokener.ai Gemini response ended without a finish reason"
                )
            break
        if continuation in seen:
            raise InvokeServerUnavailableError("Tokener.ai repeated a Gemini continuation token")
        seen.add(continuation)
        payload = {**payload, "continuationToken": continuation}
        finish = None
    else:
        raise InvokeServerUnavailableError("Tokener.ai exceeded the Gemini continuation limit")
    finish = {
        "MAX_TOKENS": "length",
        "STOP": "stop",
        "SAFETY": "content_filter",
        "RECITATION": "content_filter",
    }.get(finish, finish)
    calls = output.calls if finish == "stop" else []
    opaque = (
        {OPAQUE_KEY: output.parts}
        if any("thoughtSignature" in part for part in output.parts)
        else None
    )
    yield _wire.chunk(
        model,
        visible + output.close_thinking(),
        calls=calls,
        opaque=opaque,
        finish="tool_calls" if calls else finish,
        usage=llm._calc_response_usage(model, credentials, *tokens),
    )


def _interaction_content(result) -> list[dict]:
    parts = result.get("outputs") or [
        part
        for step in result.get("steps") or []
        if step.get("type") in {"model_output", "thought"}
        for part in step.get("content") or step.get("summary") or []
    ]
    if not parts and result.get("output_text"):
        parts = [{"type": "text", "text": result["output_text"]}]
    return parts


def _interactions(llm, model, credentials, path, payload, stream) -> Generator:
    with llm._request_at(path, credentials, json=payload, stream=stream) as response:
        output = Output()
        result = None
        emitted_types = set()
        if stream:
            for event_name, event in _sse.events(response):
                event_type = event.get("event_type") or event_name
                if event_type == "error" or event.get("error"):
                    _wire.response_error(event.get("error"))
                if event_type in {"interaction.complete", "interaction.completed"}:
                    result = event.get("interaction", event)
                    break
                if event_type not in {"content.delta", "step.delta"}:
                    continue
                delta = event.get("delta") or {}
                if parts := output.read(_interaction_parts([delta])):
                    emitted_types.add(delta.get("type"))
                    yield _wire.chunk(model, parts)
        else:
            result = response.json()
        if not isinstance(result, dict):
            raise InvokeConnectionError("Missing Gemini Interactions terminal event")
        if result.get("error") or result.get("status") in {"failed", "cancelled"}:
            _wire.response_error(result.get("error"))
        visible = output.read(
            _interaction_parts(
                [
                    part
                    for part in _interaction_content(result)
                    if part.get("type") not in emitted_types
                ]
            )
        )
        usage = result.get("usage") or {}
        yield _wire.chunk(
            model,
            visible + output.close_thinking(),
            finish="stop",
            usage=llm._calc_response_usage(
                model,
                credentials,
                usage.get("total_input_tokens") or 0,
                (usage.get("total_output_tokens") or 0) + (usage.get("total_thought_tokens") or 0),
            ),
        )


def _interaction_parts(parts) -> list[dict]:
    wire = []
    for part in parts:
        match part.get("type"):
            case "text":
                wire.append({"text": part.get("text", "")})
            case "thought_summary":
                wire.append({"text": (part.get("content") or {}).get("text", ""), "thought": True})
            case "image":
                if part.get("data"):
                    wire.append(
                        {"inlineData": {"data": part["data"], "mimeType": part["mime_type"]}}
                    )
    return wire


def invoke(llm, model, credentials, messages, params, tools, stop, stream) -> Generator:
    path, payload, interactions = _request(
        llm, model, credentials, messages, params, tools, stop, stream
    )
    generate = _interactions if interactions else _generate
    yield from generate(llm, model, credentials, path, payload, stream)
