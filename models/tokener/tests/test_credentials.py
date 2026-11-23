import json
from unittest.mock import patch

import pytest
import requests
from dify_plugin.errors.model import CredentialsValidateFailedError

from models._credentials import ENDPOINT_URL, validate_model_access
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

    provider.validate_provider_credentials({"api_key": "test-key"})

    assert get.call_args.args == (f"{ENDPOINT_URL}/models",)
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"


@patch("models._credentials.requests.get")
def test_model_validation_requires_model_access(get) -> None:
    get.return_value = response(
        200,
        {"object": "list", "data": [{"id": "allowed-model"}]},
    )

    validate_model_access({"api_key": "test-key"}, "allowed-model")

    with pytest.raises(CredentialsValidateFailedError, match="not available"):
        validate_model_access({"api_key": "test-key"}, "other-model")


@patch("models._credentials.requests.get")
def test_upstream_failure_does_not_expose_response_body(get) -> None:
    get.return_value = response(503, {"error": {"message": "internal detail"}})

    with pytest.raises(
        CredentialsValidateFailedError,
        match="validation failed with status 503",
    ) as error:
        validate_model_access({"api_key": "secret"})

    assert "internal detail" not in str(error.value)
