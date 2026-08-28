import json
from unittest.mock import patch

import pytest
import requests
from dify_plugin.errors.model import CredentialsValidateFailedError

from models._credentials import validate_model_access
from provider.tokener import TokenerModelProvider


def response(status: int, payload: object) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    result.headers["Content-Type"] = "application/json"
    return result


@patch("models._credentials.requests.get")
def test_provider_validation_uses_models_endpoint(get) -> None:
    get.return_value = response(200, {"object": "list", "data": []})
    provider = TokenerModelProvider.__new__(TokenerModelProvider)

    provider.validate_provider_credentials({"api_key": " test-key "})

    get.assert_called_once_with(
        "https://api.tokener.dev/v1/models",
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer test-key",
        },
        timeout=(10, 30),
    )


@patch("models._credentials.requests.get")
def test_model_validation_requires_model_access(get) -> None:
    get.return_value = response(
        200,
        {"object": "list", "data": [{"id": "allowed-model"}]},
    )

    validate_model_access({"api_key": "test-key"}, "allowed-model")

    with pytest.raises(CredentialsValidateFailedError, match="not available"):
        validate_model_access({"api_key": "test-key"}, "other-model")


@pytest.mark.parametrize("status", [401, 403])
@patch("models._credentials.requests.get")
def test_invalid_key_statuses_are_safe(get, status: int) -> None:
    get.return_value = response(status, {"error": {"message": "sensitive"}})

    with pytest.raises(CredentialsValidateFailedError, match="Invalid Tokener.ai API key"):
        validate_model_access({"api_key": "secret"})


@patch("models._credentials.requests.get")
def test_upstream_failure_does_not_expose_response_body(get) -> None:
    get.return_value = response(503, {"error": {"message": "internal detail"}})

    with pytest.raises(
        CredentialsValidateFailedError,
        match="validation failed with status 503",
    ) as error:
        validate_model_access({"api_key": "secret"})

    assert "internal detail" not in str(error.value)


@patch("models._credentials.requests.get")
def test_invalid_model_list_is_rejected(get) -> None:
    get.return_value = response(200, b"not-json")

    with pytest.raises(CredentialsValidateFailedError, match="invalid model list"):
        validate_model_access({"api_key": "secret"})
