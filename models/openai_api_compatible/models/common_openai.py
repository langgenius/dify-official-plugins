from collections.abc import Mapping

import openai
from httpx import Timeout

from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)


class _CommonOpenAI:
    def _to_credential_kwargs(self, credentials: Mapping) -> dict:
        """
        Transform credentials to kwargs for model instance

        :param credentials:
        :return:
        """
        # Get custom header settings
        api_key = credentials.get("openai_api_key") or credentials.get("api_key")
        api_key_header_name = credentials.get("api_key_header_name", "Authorization")
        api_key_value_prefix = credentials.get("api_key_value_prefix", "Bearer ")

        # If using non-standard Authorization header, use default_headers instead
        if api_key_header_name != "Authorization":
            credentials_kwargs = {
                "api_key": "placeholder",  # OpenAI SDK requires api_key, but we'll override the header
                "timeout": Timeout(315.0, read=300.0, write=10.0, connect=5.0),
                "max_retries": 1,
            }
            # Use default_headers to set custom header
            if api_key:
                credentials_kwargs["default_headers"] = {
                    api_key_header_name: f"{api_key_value_prefix}{api_key}"
                }
        else:
            # Standard Authorization header
            credentials_kwargs = {
                "api_key": api_key or "placeholder",
                "timeout": Timeout(315.0, read=300.0, write=10.0, connect=5.0),
                "max_retries": 1,
            }
            # If using custom prefix (not "Bearer "), use default_headers
            if api_key and api_key_value_prefix != "Bearer ":
                credentials_kwargs["default_headers"] = {
                    "Authorization": f"{api_key_value_prefix}{api_key}"
                }

        if credentials.get("openai_api_base"):
            openai_api_base = credentials["openai_api_base"].rstrip("/")
            credentials_kwargs["base_url"] = openai_api_base + "/v1"

        if credentials.get("endpoint_url"):
            endpoint_url = credentials["endpoint_url"].rstrip("/")
            credentials_kwargs["base_url"] = endpoint_url

        if "openai_organization" in credentials:
            credentials_kwargs["organization"] = credentials["openai_organization"]

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
            InvokeConnectionError: [openai.APIConnectionError, openai.APITimeoutError],
            InvokeServerUnavailableError: [openai.InternalServerError],
            InvokeRateLimitError: [openai.RateLimitError],
            InvokeAuthorizationError: [openai.AuthenticationError, openai.PermissionDeniedError],
            InvokeBadRequestError: [
                openai.BadRequestError,
                openai.NotFoundError,
                openai.UnprocessableEntityError,
                openai.APIError,
            ],
        }
