from http import HTTPStatus

import requests
from dify_plugin.errors.model import CredentialsValidateFailedError

DEFAULT_ENDPOINT_URL = "https://api.bf16.ai/v1"
VALIDATION_TIMEOUT = (10, 30)


def resolve_endpoint_url(credentials: dict) -> str:
    raw = credentials.get("endpoint_url")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().rstrip("/")
    return DEFAULT_ENDPOINT_URL


def validate_model_access(credentials: dict, model: str | None = None) -> None:
    api_key = credentials.get("api_key")
    if not isinstance(api_key, str) or not api_key.strip():
        raise CredentialsValidateFailedError("bf16.ai API key is required")

    endpoint_url = resolve_endpoint_url(credentials)
    try:
        response = requests.get(
            f"{endpoint_url}/models",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key.strip()}",
            },
            timeout=VALIDATION_TIMEOUT,
        )
    except requests.RequestException as ex:
        raise CredentialsValidateFailedError(
            "Unable to reach bf16.ai for credential validation"
        ) from ex

    if response.status_code in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
        raise CredentialsValidateFailedError("Invalid bf16.ai API key")
    if response.status_code != HTTPStatus.OK:
        raise CredentialsValidateFailedError(
            f"bf16.ai credential validation failed with status {response.status_code}"
        )

    try:
        payload = response.json()
    except ValueError as ex:
        raise CredentialsValidateFailedError("bf16.ai returned an invalid model list") from ex

    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise CredentialsValidateFailedError("bf16.ai returned an invalid model list")
    if model is not None and model not in {
        item.get("id") for item in items if isinstance(item, dict)
    }:
        raise CredentialsValidateFailedError(
            f"Model '{model}' is not available to this bf16.ai API key"
        )
