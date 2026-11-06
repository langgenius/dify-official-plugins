import json
from collections.abc import Mapping
from typing import Any

import openai
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from httpx import Timeout


class _CommonOpenAI:
    def _to_credential_kwargs(self, credentials: Mapping) -> dict:
        """
        Transform credentials to kwargs for model instance

        :param credentials:
        :return:
        """
        credentials_kwargs = {
            "api_key": credentials["api_key"],
            "timeout": Timeout(315.0, read=300.0, write=10.0, connect=5.0),
            "max_retries": 1,
        }

        if credentials.get("endpoint_url"):
            openai_api_base = credentials["endpoint_url"].rstrip("/")
            credentials_kwargs["base_url"] = openai_api_base + "/v1"

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


# Keys that carry the actual request content. Letting Extra Body override them
# would silently replace the user's prompt/documents, so they are rejected.
RESERVED_EXTRA_BODY_KEYS = frozenset(
    {"model", "messages", "prompt", "input", "query", "passages", "documents", "stream"}
)


def parse_extra_body(credentials: Mapping) -> dict[str, Any]:
    """
    Parse the optional ``extra_body`` credential (a JSON object string).

    Returns an empty dict when the field is empty. Raises ValueError with a
    readable message when the JSON is invalid, is not an object, or tries to
    override a reserved key.
    """
    raw = credentials.get("extra_body")
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        data = dict(raw)
    else:
        text = str(raw).strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError as ex:
            raise ValueError(f"Extra Body is not valid JSON: {ex.msg} (line {ex.lineno}, column {ex.colno})") from None
        if not isinstance(data, dict):
            raise ValueError('Extra Body must be a JSON object, e.g. {"truncate": "END"}')

    reserved = sorted(RESERVED_EXTRA_BODY_KEYS.intersection(data))
    if reserved:
        raise ValueError(f"Extra Body must not override reserved keys: {', '.join(reserved)}")
    return data


def merge_extra_body(payload: dict[str, Any], credentials: Mapping) -> dict[str, Any]:
    """Merge ``extra_body`` into ``payload`` in place. Extra Body wins on conflicts."""
    payload.update(parse_extra_body(credentials))
    return payload
