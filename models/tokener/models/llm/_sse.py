"""Strict chat-completion SSE framing for the SDK's OpenAI-compatible parser.

The SDK expects complete ``data: JSON`` records, but its fixed ``\n\n``
separator cannot decode standard CRLF streams. Normalize framing only; model
content, tools, reasoning, usage and provider-specific payload fields are never
rewritten. A protocol error must not become a successful empty final chunk.
"""

import codecs
import json
from collections.abc import Generator

import requests
from dify_plugin.errors.model import InvokeConnectionError, InvokeServerUnavailableError


def _lines(response: requests.Response, chunk_size: int) -> Generator[str, None, None]:
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    pending = ""
    after_cr = False
    first = True
    for chunk in response.iter_content(chunk_size=chunk_size, decode_unicode=False):
        text = decoder.decode(chunk)
        if first and text:
            text = text.removeprefix("\ufeff")
            first = False
        for character in text:
            if after_cr and character == "\n":
                after_cr = False
                continue
            after_cr = False
            if character in ("\r", "\n"):
                yield pending
                pending = ""
                after_cr = character == "\r"
            else:
                pending += character
    pending += decoder.decode(b"", final=True)
    if pending:
        # Let the record parser ignore a trailing comment/metadata field. A data
        # field without its blank record boundary is still rejected below.
        yield pending


def _records(
    response: requests.Response, chunk_size: int
) -> Generator[tuple[str, str], None, None]:
    data: list[str] = []
    event_type = ""
    for line in _lines(response, chunk_size):
        if not line:
            if data:
                yield "\n".join(data), event_type
            data = []
            event_type = ""
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "data":
            data.append(value)
        elif field == "event":
            event_type = value
        # id, retry and unrecognized fields do not affect the model payload.
    if data:
        raise InvokeConnectionError("Tokener.ai SSE stream ended inside a record")


def _reject_constant(_value: str) -> None:
    raise ValueError("Non-finite JSON number")


class ChatCompletionSSEStreamResponse(requests.Response):
    """Response adapter consumed before the existing tool-call accumulator.

    ``iter_lines`` intentionally emits complete normalized records regardless of
    the SDK's requested delimiter. ``usage_source`` records provenance only; it
    never fills, changes or estimates usage. Callers must not label SDK fallback
    token estimates as authoritative upstream usage.
    """

    def __init__(self, response: requests.Response) -> None:
        super().__init__()
        self.response = response
        self.status_code = response.status_code
        self.encoding = "utf-8"
        self.headers = response.headers.copy()
        self.usage_source = "absent"

    def close(self) -> None:
        self.response.close()

    def iter_lines(self, chunk_size=512, decode_unicode=False, delimiter=None):
        del delimiter
        saw_choice = False
        terminal = False
        try:
            for data, event_type in _records(self.response, chunk_size):
                if event_type == "error":
                    raise InvokeServerUnavailableError("Tokener.ai returned an SSE error event")
                if data == "[DONE]":
                    if not saw_choice:
                        raise InvokeConnectionError("Tokener.ai SSE stream ended without a choice")
                    return
                try:
                    payload = json.loads(data, parse_constant=_reject_constant)
                except (ValueError, TypeError) as error:
                    raise InvokeServerUnavailableError(
                        "Tokener.ai returned malformed SSE JSON"
                    ) from error
                if not isinstance(payload, dict):
                    raise InvokeServerUnavailableError("Tokener.ai returned an invalid SSE object")
                if payload.get("error") is not None:
                    raise InvokeServerUnavailableError("Tokener.ai returned an SSE error envelope")
                choices = payload.get("choices")
                if not isinstance(choices, list) or any(
                    not isinstance(choice, dict) for choice in choices
                ):
                    raise InvokeServerUnavailableError("Tokener.ai returned invalid SSE choices")
                if choices:
                    saw_choice = True
                    for choice in choices:
                        if "delta" not in choice and not (
                            isinstance(choice.get("finish_reason"), str) and choice["finish_reason"]
                        ):
                            raise InvokeServerUnavailableError(
                                "Tokener.ai returned an SSE choice without a delta or finish reason"
                            )
                        if "delta" in choice and not isinstance(choice["delta"], dict):
                            raise InvokeServerUnavailableError(
                                "Tokener.ai returned an invalid SSE delta"
                            )
                        if choice.get("index", 0) == 0 and choice.get("finish_reason") is not None:
                            terminal = True
                usage = payload.get("usage")
                if isinstance(usage, dict) and usage:
                    complete = all(
                        isinstance(usage.get(name), int)
                        and not isinstance(usage[name], bool)
                        and usage[name] >= 0
                        for name in ("prompt_tokens", "completion_tokens")
                    )
                    self.usage_source = "upstream" if complete else "upstream_partial_or_invalid"
                normalized = f"data: {json.dumps(payload, ensure_ascii=False, allow_nan=False)}"
                yield normalized if decode_unicode else normalized.encode("utf-8")
            if not saw_choice or not terminal:
                raise InvokeConnectionError("Tokener.ai SSE stream ended without a terminal event")
        except UnicodeError as error:
            raise InvokeServerUnavailableError("Tokener.ai returned invalid SSE UTF-8") from error
        except requests.RequestException as error:
            raise InvokeConnectionError("Tokener.ai SSE transport was interrupted") from error
        finally:
            self.close()
