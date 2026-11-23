import base64
import re

from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    PromptMessageContentType,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeBadRequestError

from models.llm import _gemini_files, _wire
from models.llm._gemini_output import OPAQUE_KEY

DEFAULT_THOUGHT_SIGNATURE = base64.b64encode(b"skip_thought_signature_validator").decode()
_UNSUPPORTED_DOCUMENT_TYPES = {
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
}
_UNSUPPORTED_EXTENSIONS = {
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "odt",
    "ods",
    "odp",
    "rtf",
    "wps",
    "epub",
    "mdx",
    "markdown",
}


def _normalize_opaque_part(part: dict) -> dict:
    key_map = {
        "inline_data": "inlineData",
        "file_data": "fileData",
        "function_call": "functionCall",
        "function_response": "functionResponse",
        "thought_signature": "thoughtSignature",
        "executable_code": "executableCode",
        "code_execution_result": "codeExecutionResult",
    }
    nested_map = {"mime_type": "mimeType", "file_uri": "fileUri"}
    out = {}
    for key, value in part.items():
        mapped = key_map.get(key, key)
        if isinstance(value, dict) and mapped in {"inlineData", "fileData"}:
            value = {nested_map.get(k, k): v for k, v in value.items()}
        out[mapped] = value
    return out


def prompt_text(messages) -> str:
    parts = []
    for message in messages:
        content = message.content
        if isinstance(content, list):
            content = "".join(
                item.data for item in content if item.type != PromptMessageContentType.IMAGE
            )
        speaker = "model" if isinstance(message, AssistantPromptMessage) else "user"
        text = f"\n\n{speaker}: {content}"
        if isinstance(message, AssistantPromptMessage) and message.tool_calls:
            text += "\n" + "\n".join(
                f"{call.function.name} {call.function.arguments}" for call in message.tool_calls
            )
        parts.append(text)
    return "".join(parts).rstrip()


def _parts(llm, credentials, value, *, inline: bool, remaining: list[int]) -> list[dict]:
    if isinstance(value, str):
        return [{"text": value}] if value else []
    parts = []
    for item in value or []:
        if isinstance(item, TextPromptMessageContent):
            if item.data:
                parts.append({"text": item.data})
            continue
        mime = item.mime_type
        if item.type.value == "document":
            fmt = (getattr(item, "format", None) or "").lower()
            if mime in _UNSUPPORTED_DOCUMENT_TYPES or fmt in _UNSUPPORTED_EXTENSIONS:
                continue
            if fmt == "md":
                mime = "text/markdown"
        elif (
            not mime.startswith(("image/", "audio/", "video/", "text/"))
            and mime != "application/pdf"
        ):
            raise InvokeBadRequestError("Unsupported Gemini attachment type")
        use_inline = inline or mime.startswith("image/")
        data = _gemini_files.media_bytes(
            item, max_bytes=remaining[0] if use_inline else _gemini_files.MAX_BYTES
        )
        if use_inline:
            remaining[0] -= len(data)
            parts.append(
                {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}}
            )
        else:
            uri = _gemini_files.upload(llm, credentials, mime, data)
            parts.append({"fileData": {"mimeType": mime, "fileUri": uri}})
    return parts


def _history(llm, credentials, messages, *, inline, promote=True) -> tuple[list, list]:
    system, scalar_indexes, turns = [], [], []
    remaining = [_gemini_files.MAX_BYTES]
    last_scalar = None
    structured_system = False
    fallback_system = False
    tool_calls = {}
    for message in messages:
        if message.role.value in {"system", "developer"}:
            if isinstance(message.content, str):
                last_scalar = message.content
                if message.content:
                    scalar_indexes.append(len(system))
                    system.append({"text": message.content})
                continue
            if message.content and all(
                isinstance(part, TextPromptMessageContent) and part.data for part in message.content
            ):
                parts = [{"text": part.data} for part in message.content]
                system.extend(parts)
                structured_system = True
                turns.append(("user", parts, True, False))
                continue
            fallback_system = True
        role = "model" if isinstance(message, AssistantPromptMessage) else "user"
        if isinstance(message, ToolPromptMessage):
            call_id = message.tool_call_id
            name, native_id = tool_calls.get(call_id, (message.name or call_id, call_id))
            response = {"name": name, "response": {"response": message.content}}
            if native_id:
                response["id"] = native_id
            parts = [{"functionResponse": response}]
        elif isinstance(message, AssistantPromptMessage):
            opaque = message.opaque_body if isinstance(message.opaque_body, dict) else {}
            if OPAQUE_KEY in opaque:
                stored = opaque.get(OPAQUE_KEY, [])
            elif isinstance(gc := opaque.get("gemini_content"), dict):
                stored = gc.get("parts") or []
            else:
                stored = []
            if stored:
                if not isinstance(stored, list) or not all(
                    isinstance(part, dict) for part in stored
                ):
                    raise InvokeBadRequestError("Invalid Gemini assistant history")
                normalized = [_normalize_opaque_part(part) for part in stored]
                images = iter(
                    item
                    for item in (message.content if isinstance(message.content, list) else [])
                    if isinstance(item, ImagePromptMessageContent)
                )
                rehydrated: list[dict] = []
                native_ids = set()
                for part in normalized:
                    _wire.reject_controls(part, nested=False)
                    if media := part.get("inlineData"):
                        if not isinstance(media, dict):
                            raise InvokeBadRequestError("Invalid Gemini assistant history")
                        data = media.get("data")
                        if data is None:
                            image = next(images, None)
                            if image is None:
                                raise InvokeBadRequestError(
                                    "Missing assistant image for Gemini conversation history"
                                )
                            raw_bytes = _gemini_files.media_bytes(image, max_bytes=remaining[0])
                            remaining[0] -= len(raw_bytes)
                            part = {
                                **part,
                                "inlineData": {
                                    **media,
                                    "mimeType": media.get("mimeType") or image.mime_type,
                                    "data": base64.b64encode(raw_bytes).decode(),
                                },
                            }
                        elif not isinstance(data, str):
                            raise InvokeBadRequestError("Invalid Gemini assistant history")
                        else:
                            remaining[0] -= len(_gemini_files.decode_media(data, remaining[0]))
                    rehydrated.append(part)
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
                parts = [
                    {**part, "thoughtSignature": DEFAULT_THOUGHT_SIGNATURE}
                    if "functionCall" in part and not part.get("thoughtSignature")
                    else part.copy()
                    for part in rehydrated
                ]
                for call in message.tool_calls:
                    tool_calls[call.id] = (
                        call.function.name,
                        call.id if call.id in native_ids else None,
                    )
            else:
                text = (
                    re.sub(r"^<think>.*?</think>\s*", "", message.content, count=1, flags=re.DOTALL)
                    if isinstance(message.content, str)
                    else message.content
                )
                parts = [
                    {**part, "thoughtSignature": DEFAULT_THOUGHT_SIGNATURE}
                    for part in _parts(llm, credentials, text, inline=inline, remaining=remaining)
                ]
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
                            "thoughtSignature": DEFAULT_THOUGHT_SIGNATURE,
                        }
                    )
        else:
            parts = _parts(llm, credentials, message.content, inline=inline, remaining=remaining)
        turns.append((role, parts, False, isinstance(message, UserPromptMessage)))
    ordinary = [turn for turn in turns if not turn[2]]
    if (
        promote
        and structured_system
        and not fallback_system
        and last_scalar != ""
        and ordinary
        and ordinary[0][3]
        and all(turn[1] for turn in ordinary)
    ):
        superseded = set(scalar_indexes[:-1])
        system = [part for index, part in enumerate(system) if index not in superseded]
        turns = ordinary
    else:
        system = [{"text": last_scalar}] if last_scalar else []
    contents = []
    for role, parts, _, _ in turns:
        if not parts and role == "model":
            continue
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": role, "parts": list(parts)})
    return system, contents
