import base64
import binascii
import json
import re
from pathlib import PurePosixPath
from urllib.parse import quote

import requests
from dify_plugin.config.config import DifyPluginEnv
from dify_plugin.entities.model.message import (
    PromptMessageContentType,
    UserPromptMessage,
)
from dify_plugin.errors.model import InvokeBadRequestError, InvokeError

REQUEST_BODY_LIMIT = 32 * 1024 * 1024
DOCUMENT_CONTENT_TYPES = {PromptMessageContentType.DOCUMENT, PromptMessageContentType.IMAGE}
DOCUMENT_FORMATS = {
    "txt": "text/plain",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "epub": "application/epub+zip",
    "mobi": "application/x-mobipocket-ebook",
    "md": "text/markdown",
    "csv": "text/csv",
    "json": "application/json",
    "bmp": "image/bmp",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
}


def has_documents(messages):
    return any(
        content.type in DOCUMENT_CONTENT_TYPES
        for message in messages
        if isinstance(message.content, list)
        for content in message.content
    )


def _size_error():
    return InvokeBadRequestError(
        "The document and messages exceed the 32 MiB request limit. "
        "This limit includes base64 encoding and JSON. Use a smaller document."
    )


def _credential_secrets(credentials):
    secrets = [credentials.get("api_key")]

    def collect(value, key=""):
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                collect(child_value, "authorization" if key == "extra_headers" else str(child_key))
        elif isinstance(value, (list, tuple)):
            for child_value in value:
                collect(child_value, key)
        elif isinstance(value, str) and re.search(
            r"secret|token|password|credential|api[_-]?key|authorization|auth", key, re.I
        ):
            secrets.append(value)

    collect(credentials)
    return sorted(
        {secret for secret in secrets if isinstance(secret, str) and secret}, key=len, reverse=True
    )


def _safe_error_message(response, credentials):
    message = None
    try:
        payload = response.json()
    except (ValueError, TypeError):
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            message = error["message"]
        if message is None:
            message = next(
                (
                    payload.get(key)
                    for key in ("message", "detail")
                    if isinstance(payload.get(key), str)
                ),
                None,
            )
    if not message:
        return f"The document request failed with HTTP {response.status_code}."
    secrets = _credential_secrets(credentials)
    for secret in secrets:
        encoded = quote(secret, safe="")
        if encoded != secret:
            message = message.replace(encoded, "[REDACTED]")
    message = re.sub(r"Bearer\s+[^\s\"',;]+", "Bearer [REDACTED]", message, flags=re.I)
    message = re.sub(r"\b(?:sk[-_]|rk[-_]|tkr_)[A-Za-z0-9_+/=.-]+", "[REDACTED]", message)
    for secret in secrets:
        message = message.replace(secret, "[REDACTED]")
    message = message[:500]
    return f"The document request failed with HTTP {response.status_code}: {message}"


def prepare_documents(messages):
    prepared = []
    total_bytes = 0
    for message in messages:
        if not isinstance(message.content, list):
            prepared.append(message)
            continue
        content = []
        for item in message.content:
            if item.type in {PromptMessageContentType.VIDEO, PromptMessageContentType.AUDIO}:
                raise InvokeBadRequestError(
                    "qwen-long does not support video or audio attachments."
                )
            if item.type not in DOCUMENT_CONTENT_TYPES:
                content.append(item)
                continue
            if not isinstance(message, UserPromptMessage):
                raise InvokeBadRequestError("Attach qwen-long documents to a user message.")
            extension = item.format.lower().lstrip(".")
            if extension not in DOCUMENT_FORMATS:
                raise InvokeBadRequestError(
                    "qwen-long supports TXT, DOCX, PDF, XLSX, EPUB, MOBI, MD, CSV, "
                    "JSON, BMP, PNG, JPG, JPEG, and GIF documents."
                )
            remaining = REQUEST_BODY_LIMIT * 3 // 4 - total_bytes
            if item.url:
                try:
                    with requests.get(item.url, stream=True, timeout=(10, 30)) as response:
                        response.raise_for_status()
                        body = bytearray()
                        for chunk in response.iter_content(chunk_size=65536):
                            if len(body) + len(chunk) > remaining:
                                raise _size_error()
                            body.extend(chunk)
                    raw = bytes(body)
                    encoded_data = base64.b64encode(raw).decode()
                except requests.RequestException as exc:
                    raise InvokeError(
                        "The document download failed. Attach the file again."
                    ) from exc
            else:
                if len(item.base64_data) > (remaining + 2) // 3 * 4:
                    raise _size_error()
                try:
                    raw = base64.b64decode(item.base64_data, validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise InvokeBadRequestError(
                        "The document does not contain valid base64 data."
                    ) from exc
                encoded_data = item.base64_data
            if not raw:
                raise InvokeBadRequestError("The document is empty. Attach a file with content.")
            total_bytes += len(raw)
            if total_bytes * 4 // 3 > REQUEST_BODY_LIMIT:
                raise _size_error()
            filename = PurePosixPath(item.filename.replace("\\", "/")).name
            if not filename.lower().endswith("." + extension):
                filename = f"document.{extension}"
            content.append(
                item.model_copy(
                    update={
                        "url": "",
                        "base64_data": encoded_data,
                        "mime_type": DOCUMENT_FORMATS[extension],
                        "filename": filename,
                    }
                )
            )
        prepared.append(message.model_copy(update={"content": content}))
    return prepared


def generate_documents(model, model_id, credentials, messages, parameters, stop, stream, user):
    converted = []
    for message in messages:
        if not isinstance(message, UserPromptMessage) or isinstance(message.content, str):
            converted.append(model._convert_prompt_message_to_dict(message, credentials))
            continue
        blocks = []
        for item in message.content or []:
            if item.type in DOCUMENT_CONTENT_TYPES:
                blocks.append(
                    {
                        "type": "file",
                        "file": {
                            "filename": item.filename,
                            "file_data": item.data,
                        },
                    }
                )
            else:
                single = UserPromptMessage(content=[item])
                blocks.extend(model._convert_prompt_message_to_dict(single, credentials)["content"])
        converted.append({"role": "user", "content": blocks})
    parameters = dict(parameters)
    response_format = parameters.get("response_format")
    if response_format:
        if response_format == "json_schema":
            try:
                schema = json.loads(parameters.pop("json_schema"))
                if not isinstance(schema, dict):
                    raise ValueError
            except (KeyError, ValueError, TypeError) as exc:
                raise InvokeBadRequestError(
                    "Set a valid JSON Schema for the response format."
                ) from exc
            parameters["response_format"] = {"type": "json_schema", "json_schema": schema}
        else:
            parameters["response_format"] = {"type": response_format}
    else:
        parameters.pop("json_schema", None)
    payload = {
        "model": credentials.get("endpoint_model_name", model_id),
        "stream": stream,
        **parameters,
        "messages": converted,
    }
    if stop:
        payload["stop"] = stop
    if user:
        payload["user"] = user
    if stream:
        payload["stream_options"] = {"include_usage": True}
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode(
        "utf-8", "backslashreplace"
    )
    if len(encoded) > REQUEST_BODY_LIMIT:
        raise _size_error()
    headers = {
        "Content-Type": "application/json",
        "Accept-Charset": "utf-8",
        **(credentials.get("extra_headers") or {}),
    }
    if credentials.get("api_key"):
        headers["Authorization"] = f"Bearer {credentials['api_key']}"
    response = requests.post(
        model._join_endpoint_url(credentials["endpoint_url"], "chat/completions"),
        headers=headers,
        data=encoded,
        timeout=(10, DifyPluginEnv().MAX_REQUEST_TIMEOUT),
        stream=stream,
    )
    response.encoding = "utf-8"
    if response.status_code != 200:
        try:
            message = _safe_error_message(response, credentials)
        finally:
            response.close()
        raise InvokeError(message)
    if stream:

        def chunks():
            try:
                yield from model._handle_generate_stream_response(
                    model_id, credentials, response, messages
                )
            finally:
                response.close()

        return chunks()
    try:
        return model._handle_generate_response(model_id, credentials, response, messages)
    finally:
        response.close()
