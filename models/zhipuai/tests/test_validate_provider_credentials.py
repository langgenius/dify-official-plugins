"""Regression tests for ZhipuaiProvider.validate_provider_credentials.

The provider's credential validation method must:
- accept an optional `validate_model` override in the credentials dict,
- fall back to the plugin's long-standing sentinel model when no override is
  provided, so existing installations are unaffected,
- propagate CredentialsValidateFailedError unchanged from the underlying
  model validator,
- propagate unexpected exceptions through the existing exception handler.

The override exists because `base_url` may point at a private or internal
ZhipuAI-compatible endpoint that does not host the public sentinel model.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from dify_plugin.errors.model import CredentialsValidateFailedError

# Make the plugin's own modules importable when pytest is invoked from the
# plugin directory or the repo root, matching the pattern used in the other
# models/*/tests/ files.
_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from provider.zhipuai import DEFAULT_VALIDATE_MODEL, ZhipuaiProvider  # noqa: E402


def _provider() -> ZhipuaiProvider:
    """Construct a ZhipuaiProvider without invoking ModelProvider.__init__,
    which would try to load the provider schema from disk. Stubs the
    attributes the production exception handler reads, so tests can
    exercise the error paths without a real schema.
    """
    provider = object.__new__(ZhipuaiProvider)
    provider.provider_schema = MagicMock()
    provider.provider_schema.provider = "zhipuai"
    return provider


def test_default_validate_model_is_unchanged() -> None:
    """The default sentinel keeps the value the plugin already shipped, so
    this change is behaviour-preserving for existing users.
    """
    assert DEFAULT_VALIDATE_MODEL == "glm-4.5-flash"


def test_default_validate_model_is_in_plugin_catalog() -> None:
    """Sanity check: the default sentinel exists in the plugin's model
    catalog so the validation call can actually run.
    """
    position_file = _PLUGIN_DIR / "models" / "llm" / "_position.yaml"
    assert position_file.exists(), f"missing position file: {position_file}"
    items = yaml.safe_load(position_file.read_text(encoding="utf-8")) or []
    assert DEFAULT_VALIDATE_MODEL in items, (
        f"DEFAULT_VALIDATE_MODEL={DEFAULT_VALIDATE_MODEL!r} not listed in {position_file}"
    )


def test_validate_model_is_exposed_in_the_credential_schema() -> None:
    """The override must be declared in provider_credential_schema, otherwise
    the console never collects it and the credentials dict can never carry it
    — which is the whole point of the fix for users on a custom base_url.
    """
    schema_file = _PLUGIN_DIR / "provider" / "zhipuai.yaml"
    schema = yaml.safe_load(schema_file.read_text(encoding="utf-8")) or {}
    forms = schema.get("provider_credential_schema", {}).get(
        "credential_form_schemas", []
    )
    field = next((f for f in forms if f.get("variable") == "validate_model"), None)
    assert field is not None, "validate_model missing from provider_credential_schema"
    assert field.get("required") is False, "validate_model must stay optional"
    assert field.get("default") == DEFAULT_VALIDATE_MODEL, (
        "schema default must match the code default so the UI and the "
        "fallback agree"
    )


def test_validate_provider_credentials_uses_default_when_no_override() -> None:
    """When credentials do not include `validate_model`, the provider uses
    the default sentinel.
    """
    provider = _provider()
    fake_instance = MagicMock()
    credentials = {"api_key": "test-key"}
    with patch.object(provider, "get_model_instance", return_value=fake_instance):
        provider.validate_provider_credentials(credentials=credentials)

    fake_instance.validate_credentials.assert_called_once()
    kwargs = fake_instance.validate_credentials.call_args.kwargs
    assert kwargs["model"] == DEFAULT_VALIDATE_MODEL, (
        f"expected default sentinel {DEFAULT_VALIDATE_MODEL!r}, got {kwargs['model']!r}"
    )
    assert kwargs["credentials"] == credentials


def test_validate_provider_credentials_respects_override() -> None:
    """When credentials include `validate_model`, the provider uses that
    value instead of the default. This is the internal-endpoint case: the
    private deployment hosts its own model names.
    """
    provider = _provider()
    fake_instance = MagicMock()
    override = "glm-4-internal"
    with patch.object(provider, "get_model_instance", return_value=fake_instance):
        provider.validate_provider_credentials(
            credentials={
                "api_key": "test-key",
                "base_url": "https://internal.example.com/api/paas/v4/",
                "validate_model": override,
            }
        )

    fake_instance.validate_credentials.assert_called_once()
    kwargs = fake_instance.validate_credentials.call_args.kwargs
    assert kwargs["model"] == override, (
        f"expected override {override!r}, got {kwargs['model']!r}"
    )


def test_validate_provider_credentials_treats_empty_override_as_default() -> None:
    """An empty-string `validate_model` falls back to the default rather
    than being passed through to the model validator. The console submits
    an empty string for an untouched optional text input.
    """
    provider = _provider()
    fake_instance = MagicMock()
    with patch.object(provider, "get_model_instance", return_value=fake_instance):
        provider.validate_provider_credentials(
            credentials={"api_key": "test-key", "validate_model": ""}
        )

    kwargs = fake_instance.validate_credentials.call_args.kwargs
    assert kwargs["model"] == DEFAULT_VALIDATE_MODEL, (
        f"empty override should fall back to default, got {kwargs['model']!r}"
    )


def test_validate_provider_credentials_propagates_credentials_error() -> None:
    """CredentialsValidateFailedError from the underlying model validator
    is re-raised unchanged.
    """
    provider = _provider()
    fake_instance = MagicMock()
    fake_instance.validate_credentials.side_effect = CredentialsValidateFailedError(
        "invalid api key"
    )
    with patch.object(provider, "get_model_instance", return_value=fake_instance):
        with pytest.raises(CredentialsValidateFailedError, match="invalid api key"):
            provider.validate_provider_credentials(credentials={"api_key": "x"})


def test_validate_provider_credentials_propagates_unexpected_error() -> None:
    """Unexpected exceptions from the underlying model validator are
    caught by the provider's existing handler and re-raised so Dify
    surfaces a generic failure to the user instead of crashing the
    plugin process.
    """
    provider = _provider()
    fake_instance = MagicMock()
    fake_instance.validate_credentials.side_effect = RuntimeError("network down")
    with patch.object(provider, "get_model_instance", return_value=fake_instance):
        with pytest.raises(RuntimeError, match="network down"):
            provider.validate_provider_credentials(credentials={"api_key": "x"})
