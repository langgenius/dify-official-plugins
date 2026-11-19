import codecs
import json
from collections.abc import Generator

import requests
from dify_plugin.errors.model import InvokeConnectionError, InvokeServerUnavailableError

from models.llm import _wire


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
    if data:
        raise InvokeConnectionError("Tokener.ai SSE stream ended inside a record")


def _reject_constant(_value: str) -> None:
    raise ValueError("Non-finite JSON number")


class ChatCompletionSSEStreamResponse(requests.Response):
    def __init__(self, response: requests.Response) -> None:
        super().__init__()
        self.response = response
        self.status_code = response.status_code
        self.encoding = "utf-8"
        self.headers = response.headers.copy()

    def close(self) -> None:
        self.response.close()

    def iter_lines(self, chunk_size=512, decode_unicode=False, delimiter=None):
        del delimiter
        saw_choice = False
        terminal = False
        try:
            for data, event_type in _records(self.response, chunk_size):
                if data == "[DONE]":
                    if not saw_choice or not terminal:
                        raise InvokeConnectionError(
                            "Tokener.ai SSE stream ended without a terminal event"
                        )
                    return
                try:
                    payload = json.loads(data, parse_constant=_reject_constant)
                except (ValueError, TypeError) as error:
                    raise InvokeServerUnavailableError(
                        "Tokener.ai returned malformed SSE JSON"
                    ) from error
                if not isinstance(payload, dict):
                    raise InvokeServerUnavailableError("Tokener.ai returned an invalid SSE object")
                if event_type == "error" or payload.get("error") is not None:
                    _wire.response_error(payload.get("error") or payload)
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


def events(response: requests.Response) -> Generator[tuple[str, dict], None, None]:
    try:
        for data, event_type in _records(response, 512):
            if data == "[DONE]":
                return
            try:
                payload = json.loads(data, parse_constant=_reject_constant)
            except ValueError as error:
                raise InvokeServerUnavailableError(
                    "Tokener.ai returned malformed SSE JSON"
                ) from error
            if not isinstance(payload, dict):
                raise InvokeServerUnavailableError("Tokener.ai returned an invalid SSE object")
            yield event_type or payload.get("type", ""), payload
    except UnicodeError as error:
        raise InvokeServerUnavailableError("Tokener.ai returned invalid SSE UTF-8") from error
    except requests.RequestException as error:
        raise InvokeConnectionError("Tokener.ai SSE transport was interrupted") from error
