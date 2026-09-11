"""HTTP client for the AIHubMix unified media gateway.

Two families of calls are involved:

* endpoint discovery -- ``GET /call/schema/models/{model}/endpoints`` (unauthenticated,
  describes where and how to call a model)
* generation -- ``POST /ai/v1/images/generations`` plus the task poll/content routes,
  all of which require the tenant API key.

Everything goes through :class:`AIHubMixClient` so that base URL handling, auth headers
and gateway error shapes are normalised in exactly one place.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests

DEFAULT_BASE_URL = "https://api.inferera.com"

# Discovery is cheap but the gateway still round-trips to its schema store; generation is
# the slow one because the request blocks until the upstream vendor returns the image.
DISCOVERY_TIMEOUT = 15
GENERATION_TIMEOUT = 300
DOWNLOAD_TIMEOUT = 120


class GatewayError(Exception):
    """A structured error returned by the gateway (or a transport failure)."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        tid: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.tid = tid

    def __str__(self) -> str:
        # The trace id is what support needs to find the request in gateway logs.
        details = [f"{key}={value}" for key, value in (("code", self.code), ("tid", self.tid)) if value]
        return f"{self.message} ({', '.join(details)})" if details else self.message


def error_from_payload(payload: Any, *, status: int | None = None, fallback: str) -> GatewayError:
    """Normalise ``{"error": {...}}`` bodies; fall back to a generic message."""
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, str):
        return GatewayError(error or fallback, status=status)
    if isinstance(error, dict):
        return GatewayError(
            str(error.get("message") or fallback),
            status=status,
            code=error.get("code") or error.get("type"),
            tid=error.get("tid"),
        )
    return GatewayError(fallback, status=status)


class AIHubMixClient:
    def __init__(self, credentials: dict[str, Any]) -> None:
        api_key = (credentials or {}).get("api_key")
        if not api_key:
            raise GatewayError("API Key is required")
        self.api_key = str(api_key)
        self.base_url = str(credentials.get("base_url") or DEFAULT_BASE_URL).rstrip("/")

    def url(self, path: str) -> str:
        """Absolute URL for a gateway path; ``content_url`` values already come absolute."""
        if path.startswith(("http://", "https://")):
            return path
        return urljoin(self.base_url + "/", path.lstrip("/"))

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def get_json(self, path: str, *, timeout: int = DISCOVERY_TIMEOUT, authenticated: bool = True) -> Any:
        return self._json("GET", path, timeout=timeout, authenticated=authenticated)

    def post_json(self, path: str, payload: dict[str, Any], *, timeout: int = GENERATION_TIMEOUT) -> Any:
        return self._json("POST", path, json=payload, timeout=timeout)

    def get_bytes(self, path: str, *, timeout: int = DOWNLOAD_TIMEOUT) -> bytes:
        response = self._request("GET", path, timeout=timeout, headers={"accept": "*/*"})
        if response.status_code != 200:
            raise self._error(response, fallback=f"Content download failed with HTTP {response.status_code}")
        return response.content

    def _json(
        self,
        method: str,
        path: str,
        *,
        timeout: int,
        json: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> Any:
        response = self._request(
            method,
            path,
            timeout=timeout,
            json=json,
            authenticated=authenticated,
            headers={"accept": "application/json"},
        )
        try:
            payload = response.json()
        except ValueError:
            if response.status_code == 200:
                raise GatewayError(f"Gateway returned a non-JSON body for {path}", status=200) from None
            raise GatewayError(
                f"Request to {path} failed with HTTP {response.status_code}",
                status=response.status_code,
            ) from None

        if response.status_code != 200:
            raise error_from_payload(
                payload,
                status=response.status_code,
                fallback=f"Request to {path} failed with HTTP {response.status_code}",
            )
        return payload

    def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: int,
        json: dict[str, Any] | None = None,
        authenticated: bool = True,
        headers: dict[str, str] | None = None,
    ) -> requests.Response:
        request_headers = dict(headers or {})
        if authenticated:
            request_headers.update(self.auth_headers)
        if json is not None:
            request_headers["content-type"] = "application/json"
        try:
            return requests.request(
                method,
                self.url(path),
                headers=request_headers,
                json=json,
                timeout=timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise GatewayError(f"Request to {path} timed out after {timeout}s") from exc
        except requests.exceptions.RequestException as exc:
            raise GatewayError(f"Network error calling {path}: {exc}") from exc

    def _error(self, response: requests.Response, *, fallback: str) -> GatewayError:
        try:
            return error_from_payload(response.json(), status=response.status_code, fallback=fallback)
        except ValueError:
            return GatewayError(fallback, status=response.status_code)
