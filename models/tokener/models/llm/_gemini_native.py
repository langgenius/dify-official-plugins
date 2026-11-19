import base64
import re
from collections.abc import Generator

from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
)
from dify_plugin.errors.model import InvokeBadRequestError

from models.llm import _gemini_files, _gemini_output, _wire
from models.llm._gemini_output import OPAQUE_KEY

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
    tool_calls = {}
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
            call_id = message.tool_call_id
            name, native_id = tool_calls.get(call_id, (message.name or call_id, call_id))
            response = {"name": name, "response": result}
            if native_id:
                response["id"] = native_id
            parts = [{"functionResponse": response}]
        elif isinstance(message, AssistantPromptMessage):
            stored = (
                message.opaque_body.get(OPAQUE_KEY, [])
                if isinstance(message.opaque_body, dict)
                else []
            )
            if stored:
                if not isinstance(stored, list) or not all(
                    isinstance(part, dict) for part in stored
                ):
                    raise InvokeBadRequestError("Invalid Gemini assistant history")
                native_ids = set()
                for part in stored:
                    _wire.reject_controls(part, nested=False)
                    if "functionCall" not in part:
                        continue
                    function = part["functionCall"]
                    if not isinstance(function, dict):
                        raise InvokeBadRequestError("Invalid Gemini assistant history")
                    native_id = function.get("id")
                    if native_id is not None and not isinstance(native_id, str):
                        raise InvokeBadRequestError("Invalid Gemini assistant history")
                    if native_id:
                        native_ids.add(native_id)
                parts = stored
                for call in message.tool_calls:
                    tool_calls[call.id] = (
                        call.function.name,
                        call.id if call.id in native_ids else None,
                    )
            else:
                text = (
                    _wire.without_thinking(message.content)
                    if isinstance(message.content, str)
                    else message.content
                )
                parts = _parts(llm, credentials, text, inline=inline)
                for call in message.tool_calls:
                    tool_calls[call.id] = (call.function.name, call.id)
                    parts.append(
                        {
                            "functionCall": {
                                "id": call.id,
                                "name": call.function.name,
                                "args": _wire.json_object(
                                    call.function.arguments, "Tool arguments"
                                ),
                            },
                        }
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


def invoke(llm, model, credentials, messages, params, tools, stop, stream) -> Generator:
    path, payload, interactions = _request(
        llm, model, credentials, messages, params, tools, stop, stream
    )
    generate = _gemini_output.interactions if interactions else _gemini_output.generate
    yield from generate(llm, model, credentials, path, payload, stream)
