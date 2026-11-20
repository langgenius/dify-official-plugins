import hashlib
import re
import time
from collections.abc import Generator, Iterable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, TypeVar

import openai
from dify_plugin.entities.model.llm import LLMUsage
from dify_plugin.entities.model.message import DocumentPromptMessageContent
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

T = TypeVar("T")
GPT62_MODELS = {"gpt-6.2-astra", "gpt-6.2-sol"}


def _user_digest(user: str) -> str:
    return hashlib.sha256(user.encode()).hexdigest()


def _is_gpt6_model(model: str) -> bool:
    return model.startswith(("gpt-6-", "gpt-6.1-", "gpt-6.2-"))


def _normalize_gpt6_parameters(model: str, params: dict, effort: str | None) -> None:
    if not _is_gpt6_model(model):
        return
    if model.startswith("gpt-6.2-"):
        if params.get("service_tier") == "flex":
            raise InvokeBadRequestError(
                f"{model} does not support the Flex service tier"
            )
        if effort in ("none", "minimal"):
            raise InvokeBadRequestError(
                f"{model} does not support reasoning effort {effort}"
            )
    elif model in ("gpt-6-astra", "gpt-6.1-sol") and effort == "none":
        name = "GPT-6 Astra" if model == "gpt-6-astra" else "GPT-6.1 Sol"
        raise InvokeBadRequestError(f"{name} does not support reasoning effort none")
    if effort != "none":
        for name in ("temperature", "top_p", "top_logprobs", "logprobs"):
            params.pop(name, None)
        if "include" in params:
            params["include"] = [
                item
                for item in params["include"] or []
                if item != "message.output_text.logprobs"
            ]


def field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def inline_document(document: DocumentPromptMessageContent) -> dict[str, str]:
    if document.base64_data:
        data = f"data:{document.mime_type};base64,{document.base64_data}"
    elif document.url.startswith("data:") and document.url.partition(",")[2]:
        data = document.url
    else:
        raise InvokeBadRequestError("Document input must include data")
    return {
        "filename": document.filename or f"document.{document.format.lstrip('.')}",
        "file_data": data,
    }


def apply_gpt62_pricing(
    usage: LLMUsage,
    model: str,
    details: Any,
    service_tier: str | None,
    created: float | None,
) -> LLMUsage:
    if model not in GPT62_MODELS:
        return usage

    tier_rate = 2 if service_tier in {"fast", "priority"} else 1
    if service_tier == "ultrafast":
        # The published rate changes at midnight Pacific on March 1, 2027.
        cutoff = datetime(2027, 3, 1, 8, tzinfo=UTC).timestamp()
        tier_rate = 3 if (created or time.time()) < cutoff else 6
    long_context = usage.prompt_tokens > 272_000
    usage.prompt_unit_price *= tier_rate * (2 if long_context else 1)
    usage.completion_unit_price *= tier_rate * (Decimal("1.5") if long_context else 1)

    reads = field(details, "cached_tokens") or 0
    writes = field(details, "cache_write_tokens") or 0
    writes_12h = (
        field(field(details, "cache_write_tokens_details"), "ttl_12h_tokens") or 0
    )
    ordinary = usage.prompt_tokens - reads - writes
    # Each input token belongs to exactly one of these four price classes.
    billable = (
        ordinary
        + reads * Decimal("0.05")
        + (writes - writes_12h) * Decimal("1.25")
        + writes_12h * Decimal("2.5")
    )
    usage.prompt_price = billable * usage.prompt_unit_price * usage.prompt_price_unit
    usage.completion_price = (
        usage.completion_tokens
        * usage.completion_unit_price
        * usage.completion_price_unit
    )
    usage.total_price = usage.prompt_price + usage.completion_price
    return usage


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
