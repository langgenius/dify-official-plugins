from http import HTTPStatus

import requests
from dify_plugin.errors.model import CredentialsValidateFailedError

ENDPOINT_URL = "https://api.tokener.dev/v1"
VALIDATION_TIMEOUT = (10, 30)


def validate_model_access(credentials: dict, model: str | None = None) -> None:
    api_key = credentials.get("api_key")
    if not isinstance(api_key, str) or not api_key.strip():
        raise CredentialsValidateFailedError("Tokener.ai API key is required")

    try:
        response = requests.get(
            f"{ENDPOINT_URL}/models",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            timeout=VALIDATION_TIMEOUT,
        )
    except requests.RequestException as ex:
        raise CredentialsValidateFailedError(
            "Unable to reach Tokener.ai for credential validation"
        ) from ex

    if response.status_code in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
        raise CredentialsValidateFailedError("Invalid Tokener.ai API key")
    if response.status_code != HTTPStatus.OK:
        raise CredentialsValidateFailedError(
            f"Tokener.ai credential validation failed with status {response.status_code}"
        )
    try:
        payload = response.json()
    except ValueError as ex:
        raise CredentialsValidateFailedError(
            "Tokener.ai returned an invalid model list"
        ) from ex

    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise CredentialsValidateFailedError("Tokener.ai returned an invalid model list")
    if model is not None and model not in {
        item.get("id") for item in items if isinstance(item, dict)
    }:
        raise CredentialsValidateFailedError(
            f"Model '{model}' is not available to this Tokener.ai API key"
        )
