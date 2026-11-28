"""HTTP client and parameter helpers for the Dealport REST API v1."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import requests

DEFAULT_BASE_URL = "https://app.dealport.com/api/v1"
DEFAULT_TIMEOUT_SECONDS = 30


class DealportApiError(RuntimeError):
    """Raised when a Dealport request fails validation or returns an error status."""


def normalize_base_url(raw_url: str | None) -> str:
    url = (raw_url or DEFAULT_BASE_URL).strip().rstrip("/")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise DealportApiError("Base URL must be a valid HTTPS URL without credentials or query parameters.")
    return url


def split_csv_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def parse_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return bool(value)


def sanitize_error_message(message: str, api_key: str) -> str:
    cleaned = message
    if api_key:
        cleaned = cleaned.replace(api_key, "[REDACTED]")
    return cleaned[:500]


def request_dealport(
    credentials: dict[str, Any],
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    api_key = str(credentials.get("api_key") or "").strip()
    if not api_key:
        raise DealportApiError("Dealport API key is required.")

    base_url = normalize_base_url(credentials.get("base_url"))
    url = f"{base_url}/{path.lstrip('/')}"
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "dify-dealport-plugin/0.0.1",
    }
    if json_body is not None:
        headers["Content-Type"] = "application/json"

    clean_params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    clean_body = {k: v for k, v in (json_body or {}).items() if v is not None and v != "" and v != []}

    try:
        with requests.Session() as session:
            response = session.request(
                method=method.upper(),
                url=url,
                params=clean_params or None,
                json=clean_body if json_body is not None else None,
                headers=headers,
                timeout=timeout,
                allow_redirects=False,
            )
    except requests.exceptions.Timeout as exc:
        raise DealportApiError("Dealport API request timed out.") from exc
    except requests.exceptions.RequestException as exc:
        raise DealportApiError(f"Dealport network error ({type(exc).__name__}).") from exc

    if 300 <= response.status_code < 400:
        raise DealportApiError(f"Dealport API returned an unexpected redirect (HTTP {response.status_code}).")

    payload: Any = None
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if not (200 <= response.status_code < 300):
        detail = ""
        if isinstance(payload, dict):
            err = payload.get("error") or payload.get("message") or payload.get("detail")
            if isinstance(err, dict):
                detail = str(err.get("message") or err.get("code") or "")
            elif err:
                detail = str(err)
        suffix = f": {sanitize_error_message(detail, api_key)}" if detail else ""
        raise DealportApiError(f"Dealport API error (HTTP {response.status_code}){suffix}")

    if not isinstance(payload, dict):
        raise DealportApiError("Dealport API returned a non-object JSON response.")
    return payload
