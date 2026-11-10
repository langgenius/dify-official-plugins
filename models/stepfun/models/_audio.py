"""Shared HTTP transport for StepFun's native speech APIs."""

import json

import requests
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

from .llm._metadata import apply_dify_headers_if_enabled


class StepAudioTransport:
    def _transform_invoke_error(self, error: Exception) -> InvokeError:
        if isinstance(error, InvokeError):
            return error
        return super()._transform_invoke_error(error)

    @staticmethod
    def _post_audio(credentials: dict, path: str, payload: dict, accept: str):
        host = (
            "api.stepfun.ai"
            if credentials.get("use_international_endpoint", "false") == "true"
            else "api.stepfun.com"
        )
        credentials = apply_dify_headers_if_enabled(credentials)
        headers = {
            **(credentials.get("extra_headers") or {}),
            "Authorization": f"Bearer {credentials['api_key']}",
            "Accept": accept,
        }
        response = requests.post(
            f"https://{host}/v1/{path}",
            headers=headers,
            json=payload,
            stream=True,
            timeout=(10, 300),
        )
        if response.status_code >= 400:
            status = response.status_code
            response.close()
            error = (
                InvokeAuthorizationError
                if status in (401, 403)
                else InvokeRateLimitError
                if status == 429
                else InvokeServerUnavailableError
                if status >= 500
                else InvokeBadRequestError
            )
            raise error(f"StepFun {path} failed (HTTP {status}, endpoint: {host})")
        return response

    @staticmethod
    def _events(response):
        """Read SSE data records, including comments, CRLF and multiline data."""
        response.encoding = "utf-8"
        lines = []
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                if lines:
                    data = "\n".join(lines)
                    lines = []
                    if data == "[DONE]":
                        return
                    yield json.loads(data)
            elif line.startswith("data:"):
                lines.append(line[5:].lstrip())
        if lines:
            data = "\n".join(lines)
            if data != "[DONE]":
                yield json.loads(data)

    @property
    def _invoke_error_mapping(self):
        return {
            InvokeConnectionError: [requests.ConnectionError, requests.Timeout],
            InvokeServerUnavailableError: [requests.exceptions.ChunkedEncodingError],
            InvokeBadRequestError: [ValueError, KeyError],
        }

    def _audio_stream(self, credentials, payload):
        # Mapping must wrap iteration as HTTP failures can occur after _invoke returns.
        try:
            with self._post_audio(credentials, "audio/speech", payload, "audio/mpeg") as response:
                content_type = response.headers.get("Content-Type", "").lower()
                if "json" in content_type or content_type.startswith("text/"):
                    raise InvokeServerUnavailableError("StepFun returned a non-audio response")
                received = False
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        received = True
                        yield chunk
                if not received:
                    raise InvokeServerUnavailableError("StepFun returned no audio bytes")
        except InvokeError:
            raise
        except Exception as error:
            raise self._transform_invoke_error(error) from error
