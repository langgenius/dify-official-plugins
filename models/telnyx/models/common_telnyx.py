from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import urljoin

import requests
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

DEFAULT_TELNYX_API_BASE = "https://api.telnyx.com"


class _CommonTelnyx:
    """Shared Telnyx HTTP helpers."""

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {
            InvokeConnectionError: [requests.ConnectionError, requests.Timeout],
            InvokeServerUnavailableError: [requests.HTTPError],
            InvokeRateLimitError: [],
            InvokeAuthorizationError: [],
            InvokeBadRequestError: [requests.RequestException],
        }

    def _get_api_base(self, credentials: Mapping[str, Any]) -> str:
        base = (
            credentials.get("telnyx_api_base")
            or credentials.get("api_base")
            or DEFAULT_TELNYX_API_BASE
        )
        return str(base).strip().rstrip("/") or DEFAULT_TELNYX_API_BASE

    def _build_url(self, credentials: Mapping[str, Any], path: str) -> str:
        base = self._get_api_base(credentials)
        return urljoin(base + "/", path.lstrip("/"))

    def _get_api_key(self, credentials: Mapping[str, Any]) -> str:
        api_key = credentials.get("telnyx_api_key") or credentials.get("api_key")
        if not api_key:
            raise InvokeAuthorizationError("Telnyx API key is required")
        return str(api_key)

    def _get_headers(
        self,
        credentials: Mapping[str, Any],
        *,
        json_content: bool = True,
        extra: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._get_api_key(credentials)}",
        }
        if json_content:
            headers["Content-Type"] = "application/json"
        if extra:
            headers.update(extra)
        return headers

    def _post_json(
        self,
        credentials: Mapping[str, Any],
        path: str,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        timeout: tuple[int, int] = (10, 300),
    ) -> requests.Response:
        response = requests.post(
            self._build_url(credentials, path),
            headers=self._get_headers(credentials),
            json=dict(payload),
            timeout=timeout,
            stream=stream,
        )
        self._raise_for_response(response)
        return response

    def _raise_for_response(self, response: requests.Response) -> None:
        if 200 <= response.status_code < 300:
            return
        message = self._response_error_message(response)
        if response.status_code in {401, 403}:
            raise InvokeAuthorizationError(message)
        if response.status_code == 429:
            raise InvokeRateLimitError(message)
        if response.status_code in {408, 409, 425}:
            raise InvokeConnectionError(message)
        if response.status_code >= 500:
            raise InvokeServerUnavailableError(message)
        if 400 <= response.status_code < 500:
            raise InvokeBadRequestError(message)
        raise InvokeError(message)

    @staticmethod
    def _response_error_message(response: requests.Response) -> str:
        try:
            payload = response.json()
        except Exception:
            text = getattr(response, "text", "") or ""
            return f"Telnyx API request failed with status {response.status_code}: {text}"

        if isinstance(payload, dict):
            errors = payload.get("errors")
            if errors:
                return f"Telnyx API request failed with status {response.status_code}: {errors}"
            error = payload.get("error")
            if isinstance(error, dict):
                return f"Telnyx API request failed with status {response.status_code}: {error.get('message') or error}"
            if error:
                return f"Telnyx API request failed with status {response.status_code}: {error}"
            message = payload.get("message")
            if message:
                return f"Telnyx API request failed with status {response.status_code}: {message}"
        return f"Telnyx API request failed with status {response.status_code}: {json.dumps(payload)}"
