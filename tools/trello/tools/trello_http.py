"""
A drop-in for ``requests`` used by the original tools (``from tools import trello_http as requests``).

Those tools put ``key`` and ``token`` in the URL query. This module moves them into the
Authorization header before the request is sent, so tokens never appear in URLs (proxy and
server logs, error messages). Everything else is passed through unchanged.
"""

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests as _requests
from requests import exceptions  # noqa: F401  (tools catch requests.exceptions.RequestException)

from tools.user_auth import auth_header


def _move_credentials(url: str, params: Any, headers: dict[str, str] | None) -> tuple[str, Any, dict[str, str]]:
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    found = {k: v for k, v in query if k in ("key", "token")}
    url = urlunsplit(parts._replace(query=urlencode([(k, v) for k, v in query if k not in ("key", "token")])))
    if isinstance(params, dict):
        found.update({k: params[k] for k in ("key", "token") if k in params})
        params = {k: v for k, v in params.items() if k not in ("key", "token") and v is not None}
    headers = dict(headers or {})
    if found.get("key") and found.get("token"):
        headers.update(auth_header(found["key"], found["token"]))
    return url, params, headers


def request(method: str, url: str, params: Any = None, headers: dict[str, str] | None = None, **kwargs: Any):
    url, params, headers = _move_credentials(url, params, headers)
    kwargs.setdefault("timeout", 30)
    return _requests.request(method, url, params=params, headers=headers, **kwargs)


def get(url: str, params: Any = None, **kwargs: Any):
    return request("GET", url, params=params, **kwargs)


def post(url: str, params: Any = None, **kwargs: Any):
    return request("POST", url, params=params, **kwargs)


def put(url: str, params: Any = None, **kwargs: Any):
    return request("PUT", url, params=params, **kwargs)


def delete(url: str, params: Any = None, **kwargs: Any):
    return request("DELETE", url, params=params, **kwargs)


def reason(error: Exception) -> str:
    """What Trello said, for the original tools' "Failed to ..." messages (the URL holds no credentials)."""
    response = getattr(error, "response", None)
    if response is None:
        return str(error) or error.__class__.__name__
    detail = (response.text or "").strip()[:300]
    return f"Trello API error {response.status_code}" + (f": {detail}" if detail else "")
