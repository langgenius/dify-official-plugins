from typing import Mapping
from urllib.parse import urlparse, urlunparse

import requests

from dashscope.common.error import (
    AuthenticationError,
    InvalidParameter,
    RequestFailure,
    ServiceUnavailableError,
    UnsupportedHTTPMethod,
    UnsupportedModel,
)

from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

DEFAULT_HTTP_BASE_ADDRESS = "https://dashscope.aliyuncs.com/api/v1"
DEFAULT_WS_BASE_ADDRESS = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
INTL_HTTP_BASE_ADDRESS = "https://dashscope-intl.aliyuncs.com/api/v1"
INTL_WS_BASE_ADDRESS = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference"
DEFAULT_COMPATIBLE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
INTL_COMPATIBLE_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


def _custom_dashscope_api_base(credentials: Mapping[str, str]) -> str | None:
    raw = credentials.get("dashscope_api_base")
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    return stripped or None


def _normalize_native_http_base(url: str) -> str:
    """Return a DashScope SDK native HTTP base (typically .../api/v1).

    Accepts Alibaba Cloud Model Studio workspace URLs in either native
    ``/api/v1`` or OpenAI-compatible ``/compatible-mode/v1`` form, and a
    host-only origin which is treated as ``/api/v1``.
    """
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise InvokeBadRequestError(
            "DashScope API Base URL must be an http(s) URL, for example "
            "https://<workspace-id>.cn-beijing.maas.aliyuncs.com/api/v1"
        )
    path = parsed.path.rstrip("/")
    if path.endswith("/compatible-mode/v1"):
        path = f"{path[: -len('/compatible-mode/v1')]}/api/v1"
    elif path in ("", "/"):
        path = "/api/v1"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def get_http_base_address(credentials: Mapping[str, str]) -> str:
    custom = _custom_dashscope_api_base(credentials)
    if custom:
        return _normalize_native_http_base(custom)
    if credentials.get("use_international_endpoint", "false") == "true":
        return INTL_HTTP_BASE_ADDRESS
    return DEFAULT_HTTP_BASE_ADDRESS


def get_ws_base_address(credentials: Mapping[str, str]) -> str:
    custom = _custom_dashscope_api_base(credentials)
    if custom:
        http_base = _normalize_native_http_base(custom)
        parsed = urlparse(http_base)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        path = parsed.path.rstrip("/")
        if path.endswith("/api/v1"):
            ws_path = f"{path[: -len('/api/v1')]}/api-ws/v1/inference"
        else:
            ws_path = "/api-ws/v1/inference"
        return urlunparse((scheme, parsed.netloc, ws_path, "", "", ""))
    if credentials.get("use_international_endpoint", "false") == "true":
        return INTL_WS_BASE_ADDRESS
    return DEFAULT_WS_BASE_ADDRESS


def get_openai_compatible_base_url(credentials: Mapping[str, str]) -> str:
    custom = _custom_dashscope_api_base(credentials)
    if custom:
        http_base = _normalize_native_http_base(custom)
        if http_base.endswith("/api/v1"):
            return f"{http_base[: -len('/api/v1')]}/compatible-mode/v1"
        return http_base
    if credentials.get("use_international_endpoint", "false") == "true":
        return INTL_COMPATIBLE_BASE_URL
    return DEFAULT_COMPATIBLE_BASE_URL


class _CommonTongyi:
    @staticmethod
    def _to_credential_kwargs(credentials: dict) -> dict:
        credentials_kwargs = {
            "dashscope_api_key": credentials["dashscope_api_key"],
        }

        return credentials_kwargs

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        The key is the error type thrown to the caller
        The value is the error type thrown by the model,
        which needs to be converted into a unified error type for the caller.

        :return: Invoke error mapping
        """
        return {
            InvokeConnectionError: [
                RequestFailure,
                # The DashScope SDK lets transport-level failures propagate unwrapped.
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
            ],
            InvokeServerUnavailableError: [
                ServiceUnavailableError,
            ],
            InvokeRateLimitError: [],
            InvokeAuthorizationError: [
                AuthenticationError,
            ],
            InvokeBadRequestError: [
                InvalidParameter,
                UnsupportedModel,
                UnsupportedHTTPMethod,
            ],
        }
