from collections.abc import Generator

from dify_plugin.entities.model.message import ImagePromptMessageContent, TextPromptMessageContent
from dify_plugin.errors.model import InvokeConnectionError, InvokeServerUnavailableError

from models.llm import _sse, _wire

OPAQUE_KEY = "gemini_parts"


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


def generate(llm, model, credentials, path, payload, stream) -> Generator:
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
        if calls or any("thoughtSignature" in part for part in output.parts)
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


def interactions(llm, model, credentials, path, payload, stream) -> Generator:
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
