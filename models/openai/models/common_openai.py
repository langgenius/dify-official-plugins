from collections.abc import Generator, Iterable, Mapping
import hashlib
from typing import TypeVar

import openai
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

T = TypeVar("T")


def _user_digest(user: str) -> str:
    return hashlib.sha256(user.encode()).hexdigest()


class _CommonOpenAI:
    def _transform_invoke_error(self, error: Exception) -> InvokeError:
        if isinstance(error, InvokeError):
            return error
        return super()._transform_invoke_error(error)

    def _to_credential_kwargs(self, credentials: Mapping) -> dict:
        credentials_kwargs = {
            "api_key": credentials["openai_api_key"],
        }

        if base_url := credentials.get("openai_api_base"):
            base_url = base_url.rstrip("/")
            credentials_kwargs["base_url"] = (
                base_url if base_url.endswith("/v1") else f"{base_url}/v1"
            )

        if organization := credentials.get("openai_organization"):
            credentials_kwargs["organization"] = organization

        return credentials_kwargs

    def _stream_with_error_mapping(
        self, stream: Iterable[T]
    ) -> Generator[T, None, None]:
        try:
            yield from stream
        except Exception as error:
            transformed = self._transform_invoke_error(error)
            if transformed is error:
                raise
            raise transformed from error

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {
            InvokeConnectionError: [openai.APIConnectionError, openai.APITimeoutError],
            InvokeServerUnavailableError: [openai.InternalServerError],
            InvokeRateLimitError: [openai.RateLimitError],
            InvokeAuthorizationError: [
                openai.AuthenticationError,
                openai.PermissionDeniedError,
            ],
            InvokeBadRequestError: [
                openai.BadRequestError,
                openai.NotFoundError,
                openai.UnprocessableEntityError,
                openai.APIError,
            ],
        }
