from collections.abc import Mapping

import openai
from dify_plugin.errors.model import (InvokeAuthorizationError,
                                      InvokeBadRequestError,
                                      InvokeConnectionError, InvokeError,
                                      InvokeRateLimitError,
                                      InvokeServerUnavailableError)
from httpx import Timeout

from ._metadata import apply_dify_headers_if_enabled


class _CommonOpenAI:
    def _to_credential_kwargs(self, credentials: Mapping) -> dict:
        """
        Transform credentials to kwargs for model instance

        :param credentials:
        :return:
        """
        credentials_kwargs = {
            "api_key": credentials['openai_api_key'],
            "timeout": Timeout(315.0, read=300.0, write=10.0, connect=5.0),
            "max_retries": 1,
        }

        if credentials.get("openai_api_base"):
            openai_api_base = credentials["openai_api_base"].rstrip("/")
            credentials_kwargs["base_url"] = openai_api_base + "/v1"

        if 'openai_organization' in credentials:
            credentials_kwargs['organization'] = credentials['openai_organization']

        # Run the opt-in helper so any caller-supplied
        # ``extra_headers`` (or the Dify default headers when
        # ``enable_request_metadata`` is ``"enabled"``) are written
        # into ``credentials['extra_headers']`` BEFORE we read it
        # back below to populate ``default_headers=`` on the OpenAI
        # client constructor. The OpenAI SDK sends every entry of
        # ``default_headers`` on each outbound request, which is the
        # carrier for the Dify observability headers.
        apply_dify_headers_if_enabled(credentials)  # type: ignore[arg-type]
        credentials_kwargs["default_headers"] = credentials.get("extra_headers", {})

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
