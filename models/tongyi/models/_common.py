import re
from typing import Mapping

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

DEFAULT_API_HOST = "dashscope.aliyuncs.com"
INTL_API_HOST = "dashscope-intl.aliyuncs.com"

# Paths appended to the API host. Model Studio keeps these identical across the
# shared DashScope hosts and the per-workspace hosts, so only the host varies.
HTTP_API_PATH = "/api/v1"
WS_API_PATH = "/api-ws/v1/inference"
COMPATIBLE_API_PATH = "/compatible-mode/v1"

DEFAULT_HTTP_BASE_ADDRESS = f"https://{DEFAULT_API_HOST}{HTTP_API_PATH}"
DEFAULT_WS_BASE_ADDRESS = f"wss://{DEFAULT_API_HOST}{WS_API_PATH}"
INTL_HTTP_BASE_ADDRESS = f"https://{INTL_API_HOST}{HTTP_API_PATH}"
INTL_WS_BASE_ADDRESS = f"wss://{INTL_API_HOST}{WS_API_PATH}"

_KNOWN_API_PATHS = (COMPATIBLE_API_PATH, WS_API_PATH, HTTP_API_PATH)


def normalize_api_host(api_host: str | None) -> str:
    """Reduce a user-supplied API host to a bare ``host[:port]``.

    Model Studio hands out a bare host (e.g. ``llm-xxx.cn-beijing.maas.aliyuncs.com``),
    but users routinely paste a full Base URL instead. Accept both by stripping the
    scheme and any of the documented API paths.

    :param api_host: raw credential value, may be None or blank
    :return: normalized host, or an empty string when nothing usable was given
    """
    host = (api_host or "").strip()
    if not host:
        return ""
    host = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", host)
    host = host.strip("/")
    for path in _KNOWN_API_PATHS:
        suffix = path.strip("/")
        if host.lower().endswith(f"/{suffix}"):
            host = host[: -(len(suffix) + 1)]
            break
    return host.strip("/")


def get_api_host(credentials: Mapping[str, str]) -> str:
    """Resolve the API host to call.

    A custom ``api_host`` wins so workspace-specific hosts can be used; otherwise
    fall back to the shared DashScope hosts selected by ``use_international_endpoint``.
    """
    api_host = normalize_api_host(credentials.get("api_host"))
    if api_host:
        return api_host
    if credentials.get("use_international_endpoint", "false") == "true":
        return INTL_API_HOST
    return DEFAULT_API_HOST


def get_http_base_address(credentials: Mapping[str, str]) -> str:
    return f"https://{get_api_host(credentials)}{HTTP_API_PATH}"


def get_ws_base_address(credentials: Mapping[str, str]) -> str:
    return f"wss://{get_api_host(credentials)}{WS_API_PATH}"


def get_compatible_base_url(credentials: Mapping[str, str]) -> str:
    """OpenAI-compatible Base URL, used by models without a DashScope-native API."""
    return f"https://{get_api_host(credentials)}{COMPATIBLE_API_PATH}"


def has_custom_api_host(credentials: Mapping[str, str]) -> bool:
    return bool(normalize_api_host(credentials.get("api_host")))


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
