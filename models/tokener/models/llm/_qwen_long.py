import base64
import mimetypes
from pathlib import Path

from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    DocumentPromptMessageContent,
    SystemPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeBadRequestError

DOCUMENT_MAX_BYTES = 150 * 1024 * 1024
IMAGE_MAX_BYTES = 20 * 1024 * 1024
MAX_DOCUMENTS = 100
READ_CHUNK_BYTES = 1024 * 1024
IMAGE_FORMATS = {"bmp", "gif", "jpeg", "jpg", "png"}
REQUEST_TIMEOUT_SECONDS = MAX_DOCUMENTS * 120 + 240 + 600 + MAX_DOCUMENTS * 2 * 10 + 60


def _document(content):
    data = content.base64_data
    limit = (
        IMAGE_MAX_BYTES
        if content.mime_type.lower().startswith("image/")
        or content.format.lower().lstrip(".") in IMAGE_FORMATS
        else DOCUMENT_MAX_BYTES
    )
    if not data:
        raise InvokeBadRequestError("Qwen-Long documents require base64 data")
    if len(data) > 4 * ((limit + 2) // 3):
        raise InvokeBadRequestError("Qwen-Long document exceeds the supported file size")
    size = 0
    try:
        for offset in range(0, len(data), READ_CHUNK_BYTES):
            encoded = data[offset : offset + READ_CHUNK_BYTES]
            if offset + READ_CHUNK_BYTES < len(data) and "=" in encoded:
                raise ValueError("Intermediate base64 padding")
            size += len(base64.b64decode(encoded, validate=True))
            if size > limit:
                raise InvokeBadRequestError("Qwen-Long document exceeds the supported file size")
    except ValueError as error:
        raise InvokeBadRequestError("Qwen-Long document contains invalid base64 data") from error
    filename = Path(content.filename).name or f"document.{content.format.lstrip('.')}"
    mime_type = content.mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return {
        "type": "file",
        "file": {
            "filename": filename,
            "file_data": f"data:{mime_type};base64,{data}",
        },
    }


def convert(messages, tools):
    if tools:
        raise InvokeBadRequestError("Qwen-Long does not support tools")
    documents = [
        item
        for message in messages
        if isinstance(message.content, list)
        for item in message.content
        if isinstance(item, DocumentPromptMessageContent)
    ]
    if len(documents) > MAX_DOCUMENTS or sum(len(item.base64_data) for item in documents) > 4 * (
        (DOCUMENT_MAX_BYTES + 2) // 3
    ):
        raise InvokeBadRequestError("Qwen-Long documents exceed the request limit")
    result = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if isinstance(message, UserPromptMessage):
            texts = []
            files = []
            while index < len(messages) and isinstance(messages[index], UserPromptMessage):
                message = messages[index]
                if isinstance(message.content, list):
                    for item in message.content:
                        if isinstance(item, DocumentPromptMessageContent):
                            files.append(_document(item))
                        elif not isinstance(item, TextPromptMessageContent):
                            raise InvokeBadRequestError(
                                "Qwen-Long only supports text and documents"
                            )
                texts.append(message.get_text_content().strip())
                index += 1
            question = "\n".join(text for text in texts if text)
            if not question:
                raise InvokeBadRequestError("Qwen-Long requires a non-empty text question")
            result.append(
                {
                    "role": "user",
                    "content": [{"type": "text", "text": question}, *files] if files else question,
                }
            )
            continue
        if not isinstance(message, (SystemPromptMessage, AssistantPromptMessage)) or (
            isinstance(message.content, list)
            and any(not isinstance(item, TextPromptMessageContent) for item in message.content)
        ):
            raise InvokeBadRequestError("Qwen-Long requires text system and assistant messages")
        text = message.get_text_content()
        if isinstance(message, SystemPromptMessage):
            if text.strip():
                result.append({"role": "system", "content": text.strip()})
        else:
            result.append({"role": "assistant", "content": text or " "})
        index += 1
    return result
