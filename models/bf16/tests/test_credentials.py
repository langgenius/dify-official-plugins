import json
from unittest.mock import patch

import pytest
import requests
from dify_plugin.errors.model import CredentialsValidateFailedError

from models._credentials import resolve_endpoint_url, validate_model_access
from provider.bf16 import Bf16ModelProvider


def _response(status: int, payload: object) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    result.headers["Content-Type"] = "application/json"
    return result


def test_resolve_endpoint_url_defaults_and_trims() -> None:
    assert resolve_endpoint_url({}) == "https://api.bf16.ai/v1"
    assert resolve_endpoint_url({"endpoint_url": "  "}) == "https://api.bf16.ai/v1"
    assert (
        resolve_endpoint_url({"endpoint_url": "https://gateway.example.com/v1/"})
        == "https://gateway.example.com/v1"
    )


@patch("models._credentials.requests.get")
def test_provider_validation_uses_models_endpoint(get) -> None:
    get.return_value = _response(200, {"object": "list", "data": []})
    provider = Bf16ModelProvider.__new__(Bf16ModelProvider)

    provider.validate_provider_credentials({"api_key": "sk-bf16-v1-test"})

    get.assert_called_once_with(
        "https://api.bf16.ai/v1/models",
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer sk-bf16-v1-test",
        },
        timeout=(10, 30),
    )


@patch("models._credentials.requests.get")
def test_model_validation_checks_model_availability(get) -> None:
    get.return_value = _response(
        200,
        {"object": "list", "data": [{"id": "zai-org/glm-5.3-uncensored"}]},
    )

    validate_model_access({"api_key": "sk-bf16-v1-test"}, "zai-org/glm-5.3-uncensored")

    with pytest.raises(CredentialsValidateFailedError, match="not available"):
        validate_model_access({"api_key": "sk-bf16-v1-test"}, "unknown/model")


def test_missing_api_key_rejected() -> None:
    with pytest.raises(CredentialsValidateFailedError, match="API key is required"):
        validate_model_access({"api_key": "  "})


@pytest.mark.parametrize("status", [401, 403])
@patch("models._credentials.requests.get")
def test_invalid_key_statuses_do_not_leak_body(get, status: int) -> None:
    get.return_value = _response(status, {"error": {"message": "sensitive detail"}})

    with pytest.raises(CredentialsValidateFailedError, match="Invalid bf16.ai API key") as err:
        validate_model_access({"api_key": "secret"})

    assert "sensitive detail" not in str(err.value)


@patch("models._credentials.requests.get")
def test_upstream_failure_hides_response_body(get) -> None:
    get.return_value = _response(503, {"error": {"message": "internal detail"}})

    with pytest.raises(
        CredentialsValidateFailedError,
        match="validation failed with status 503",
    ) as err:
        validate_model_access({"api_key": "secret"})

    assert "internal detail" not in str(err.value)


@patch("models._credentials.requests.get")
def test_invalid_json_is_rejected(get) -> None:
    get.return_value = _response(200, b"not-json")

    with pytest.raises(CredentialsValidateFailedError, match="invalid model list"):
        validate_model_access({"api_key": "secret"})
