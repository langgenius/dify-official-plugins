from collections.abc import Mapping

import openai
from httpx import Timeout

from dify_plugin.errors.model import InvokeAuthorizationError, InvokeBadRequestError, InvokeConnectionError, InvokeError, InvokeRateLimitError, InvokeServerUnavailableError


class _CommonOpenAI:
    def _to_credential_kwargs(self, credentials: Mapping) -> dict:
        """
        Transform credentials to kwargs for model instance

        :param credentials:
        :return:
        """
        credentials_kwargs = {
            "api_key": credentials['api_key'],
            "timeout": Timeout(315.0, read=300.0, write=10.0, connect=5.0),
            "max_retries": 1,
        }

        # DeerAPI uses fixed base URL
        credentials_kwargs["base_url"] = "https://api.deerapi.com/v1"

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
