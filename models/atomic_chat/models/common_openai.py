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
        credentials_kwargs = {
            "api_key": credentials.get("api_key") or "atomic-chat",
            "timeout": Timeout(315.0, read=300.0, write=10.0, connect=5.0),
            "max_retries": 1,
        }

        endpoint_url = credentials.get("endpoint_url")
        if endpoint_url:
            credentials_kwargs["base_url"] = endpoint_url.rstrip("/")

        return credentials_kwargs

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
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
