"""Credential validation must actually exercise the key, not just reach the gateway."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("dify_plugin", reason="the Dify SDK is only installed in the plugin runtime")

from dify_plugin.errors.tool import ToolProviderCredentialValidationError  # noqa: E402

from utils.client import GatewayError  # noqa: E402


def _provider_class():
    path = Path(__file__).resolve().parents[1] / "provider" / "aihubmix-image.py"
    spec = importlib.util.spec_from_file_location("aihubmix_image_provider", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def provider(monkeypatch):
    module = _provider_class()
    calls: list[str] = []

    class FakeClient:
        def __init__(self, credentials):
            if not (credentials or {}).get("api_key"):
                raise GatewayError("API Key is required")

        def get_json(self, path, **kwargs):
            calls.append(path)
            return {"object": "billing_subscription"}

    monkeypatch.setattr(module, "AIHubMixClient", FakeClient)
    instance = object.__new__(module.AIHubMixImageProvider)
    return module, instance, calls


def test_validation_uses_a_route_that_checks_the_key(provider):
    module, instance, calls = provider
    instance._validate_credentials({"api_key": "k"})
    # /v1/models and /api/v1/models answer 200 for any key at all, so they cannot validate one.
    assert calls == [module.CREDENTIAL_CHECK_PATH]
    assert "models" not in module.CREDENTIAL_CHECK_PATH


def test_a_rejected_key_is_reported_as_an_invalid_key(provider):
    module, instance, _ = provider

    class Rejecting:
        def __init__(self, credentials):
            pass

        def get_json(self, path, **kwargs):
            raise GatewayError("invalid key", status=401)

    module.AIHubMixClient = Rejecting
    with pytest.raises(ToolProviderCredentialValidationError, match="Invalid API Key"):
        instance._validate_credentials({"api_key": "nope"})


def test_a_missing_key_is_reported_rather_than_crashing(provider):
    _, instance, _ = provider
    with pytest.raises(ToolProviderCredentialValidationError, match="API Key is required"):
        instance._validate_credentials({})


def test_the_provider_declaration_actually_carries_the_api_key_credential():
    """Dify parses the provider YAML through the SDK entity; a wrong key name silently
    yields a provider with no credentials, so the console offers no way to enter the key
    and every dynamic-select dropdown stays empty."""
    import yaml
    from dify_plugin.entities.tool import ToolProviderConfiguration

    root = Path(__file__).resolve().parents[1]
    declaration = yaml.safe_load((root / "provider" / "aihubmix-image.yaml").read_text())
    provider = ToolProviderConfiguration(**declaration)

    credentials = {config.name: config for config in provider.credentials_schema}
    assert set(credentials) == {"api_key", "base_url"}
    assert credentials["api_key"].required
    assert credentials["api_key"].type.value == "secret-input"
    assert credentials["base_url"].default == "https://api.inferera.com"
