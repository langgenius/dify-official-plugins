"""Tests for OrukProvider credential validation delegation."""

from unittest.mock import MagicMock, patch

import pytest
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

from provider.oruk import OrukProvider

CREDENTIALS = {
    "api_key": "oruk-test-key",
    "endpoint_url": "https://speech-api.oruk.ai/v1",
}


def _provider() -> OrukProvider:
    return object.__new__(OrukProvider)


def test_valid_credentials_delegate_to_speech2text_model():
    provider = _provider()
    model_instance = MagicMock()

    with patch.object(
        OrukProvider, "get_model_instance", return_value=model_instance
    ) as get_model:
        provider.validate_provider_credentials(CREDENTIALS)

    get_model.assert_called_once_with(ModelType.SPEECH2TEXT)
    model_instance.validate_credentials.assert_called_once_with(
        model="oruk-fourier-2b", credentials=CREDENTIALS
    )


def test_invalid_credentials_raise_credentials_validate_failed_error():
    provider = _provider()
    model_instance = MagicMock()
    model_instance.validate_credentials.side_effect = CredentialsValidateFailedError(
        "Authentication failed"
    )

    with (
        patch.object(OrukProvider, "get_model_instance", return_value=model_instance),
        pytest.raises(CredentialsValidateFailedError, match="Authentication failed"),
    ):
        provider.validate_provider_credentials(CREDENTIALS)


def test_unexpected_errors_propagate():
    provider = _provider()
    model_instance = MagicMock()
    boom = RuntimeError("unexpected failure")
    model_instance.validate_credentials.side_effect = boom

    with (
        patch.object(OrukProvider, "get_model_instance", return_value=model_instance),
        patch.object(OrukProvider, "get_provider_schema", return_value=MagicMock(provider="oruk")),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            provider.validate_provider_credentials(CREDENTIALS)
        assert exc_info.value is boom
