from dify_plugin.errors.model import InvokeConnectionError

from models.llm import _sse, _wire

OPAQUE_KEY = "anthropic_thinking"


def _stream(response, model):
    usage, blocks, arguments = {}, {}, {}
    reason, stop_details, started, stopped = None, None, False, False
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
                if event["delta"].get("stop_details") is not None:
                    stop_details = event["delta"].get("stop_details")
                usage.update(event.get("usage") or {})
            case "message_stop":
                stopped = True
                break
    if not started or not stopped:
        raise InvokeConnectionError("Tokener.ai Messages stream ended without a terminal event")
    return [block for _, block in sorted(blocks.items())], usage, reason, stop_details


def _result(blocks, *, discard_calls: bool = False):
    content, calls, thinking = [], [], []
    for block in blocks:
        match block.get("type"):
            case "thinking":
                if think_text := block.get("thinking"):
                    content.append(f"<think>\n{think_text}\n</think>\n\n")
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
