from typing import Mapping

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


def get_http_base_address(credentials: Mapping[str, str]) -> str:
    if credentials.get("use_international_endpoint", "false") == "true":
        return INTL_HTTP_BASE_ADDRESS
    return DEFAULT_HTTP_BASE_ADDRESS


def get_ws_base_address(credentials: Mapping[str, str]) -> str:
    if credentials.get("use_international_endpoint", "false") == "true":
        return INTL_WS_BASE_ADDRESS
    return DEFAULT_WS_BASE_ADDRESS


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
