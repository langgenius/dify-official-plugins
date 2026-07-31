"""Regression test for provider-level credential validation.

``FunASRProvider.validate_provider_credentials`` was a bare ``pass``, so the
provider accepted any Server URL: configuring the plugin against a host with
nothing listening saved green and enabled all four predefined models, while the
model path (Add Model) correctly rejected the same URL with ``Could not reach
FunASR endpoint``. The checking code already existed —
``models/speech2text/speech2text.py`` implements a real ``validate_credentials``
that probes the OpenAI-compatible ``/v1/models`` and falls back to a direct
reachability check — it was simply never called from the provider class. The fix
delegates to it, matching the pattern used by 44 of the 48 providers in this repo
that validate provider-level credentials.

These tests mock at the model-instance boundary, so no network call is made.
"""

from unittest.mock import MagicMock, patch

from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError

from provider.funasr import FunASRProvider


CREDENTIALS = {"endpoint_url": "http://127.0.0.1:8000/v1", "api_key": ""}


def _provider() -> FunASRProvider:
    """Build the provider without running the SDK's __init__, as the OpenAI
    plugin's own provider tests do."""
    return object.__new__(FunASRProvider)


def test_valid_credentials_delegate_to_the_speech2text_model():
    provider = _provider()
    model_instance = MagicMock()

    with patch.object(FunASRProvider, "get_model_instance", return_value=model_instance) as get_model:
        provider.validate_provider_credentials(CREDENTIALS)

    get_model.assert_called_once_with(ModelType.SPEECH2TEXT)
    model_instance.validate_credentials.assert_called_once_with(
        model="sensevoice", credentials=CREDENTIALS
    )


def test_unreachable_endpoint_is_rejected():
    """The defect: this used to pass silently, so an unreachable server saved
    green at provider level."""
    provider = _provider()
    model_instance = MagicMock()
    model_instance.validate_credentials.side_effect = CredentialsValidateFailedError(
        "Could not reach FunASR endpoint 'http://127.0.0.1:8000/v1'"
    )

    with patch.object(FunASRProvider, "get_model_instance", return_value=model_instance):
        try:
            provider.validate_provider_credentials(CREDENTIALS)
        except CredentialsValidateFailedError as exc:
            assert "Could not reach FunASR endpoint" in str(exc)
        else:
            raise AssertionError("unreachable endpoint must raise CredentialsValidateFailedError")


def test_unexpected_errors_are_not_swallowed():
    """A non-credential failure must propagate rather than be reported as a
    successful configuration."""
    provider = _provider()
    model_instance = MagicMock()
    error = RuntimeError("boom")
    model_instance.validate_credentials.side_effect = error

    with (
        patch.object(FunASRProvider, "get_model_instance", return_value=model_instance),
        patch.object(FunASRProvider, "get_provider_schema", return_value=MagicMock(provider="funasr")),
    ):
        try:
            provider.validate_provider_credentials(CREDENTIALS)
        except RuntimeError as exc:
            assert exc is error
        else:
            raise AssertionError("unexpected errors must propagate")
