from collections.abc import Generator, Iterable, Mapping
import hashlib
import re
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


def _chat_completions_tools_reasoning_guidance(error: Exception) -> str | None:
    if not isinstance(error, openai.BadRequestError):
        return None

    body = error.body
    if isinstance(body, Mapping):
        nested_error = body.get("error")
        if isinstance(nested_error, Mapping):
            body = nested_error
        body_message = body.get("message")
    else:
        body_message = None

    message = body_message if isinstance(body_message, str) else str(error)
    normalized_message = message.lower()
    if not all(
        token in normalized_message
        for token in ("function tools", "reasoning_effort", "/v1/chat/completions")
    ):
        return None

    model_match = re.search(r"\bgpt-(\d+(?:\.\d+)*)", message, re.IGNORECASE)
    model_label = f"GPT-{model_match.group(1)}" if model_match else "The selected model"
    return (
        f"{model_label} cannot use tools with reasoning enabled through the Chat Completions API.\n"
        "To fix this, open the model's API Key Authorization Configuration, change API Protocol "
        "from Chat Completions to Responses, save the configuration, and try again."
    )


class _CommonOpenAI:
    def _transform_invoke_error(self, error: Exception) -> InvokeError:
        if isinstance(error, InvokeError):
            return error
        if guidance := _chat_completions_tools_reasoning_guidance(error):
            return InvokeBadRequestError(guidance)
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
