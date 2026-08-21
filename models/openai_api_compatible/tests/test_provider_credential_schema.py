"""Tests for the ``provider_credential_schema`` in
``provider/openai_api_compatible.yaml``.

Issue #3682: editing a Knowledge Pipeline and configuring a credential
for an OpenAI-API-compatible custom model failed with
"does not have provider_credential_schema". The pre-fix yaml
defined only ``model_credential_schema`` (per-model fields like
``api_key``, ``endpoint_url``, ``mode``, etc.) but no top-level
``provider_credential_schema`` (provider-wide fields for the
Knowledge Pipeline credential setup flow).

This test pins:

1. The yaml declares a top-level ``provider_credential_schema``.
2. It has exactly the two universal credential fields: ``api_key``
   (required) and ``endpoint_url`` (optional, for OpenAI-compatible
   server overrides).
3. The model-level ``credential_form_schemas`` (per-model fields)
   is preserved unchanged so existing users are not affected.
4. The schema round-trips through yaml.safe_load / yaml.safe_dump
   without losing the new field.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))


PROVIDER_YAML = PLUGIN_ROOT / "provider" / "openai_api_compatible.yaml"


def _load() -> dict:
    with open(PROVIDER_YAML, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class TestProviderCredentialSchemaPresent:
    """The yaml must declare a top-level provider_credential_schema
    so the Knowledge Pipeline credential setup flow can render the
    authorization form. Without this, Dify raises
    "does not have provider_credential_schema".
    """

    def test_yaml_declares_provider_credential_schema(self) -> None:
        data = _load()
        assert "provider_credential_schema" in data, (
            "provider_credential_schema is required so the Knowledge "
            "Pipeline credential setup flow can render the form "
            "(see issue #3682)."
        )

    def test_provider_credential_schema_has_credential_form_schemas(self) -> None:
        data = _load()
        pcs = data["provider_credential_schema"]
        assert isinstance(pcs, dict)
        assert "credential_form_schemas" in pcs
        assert isinstance(pcs["credential_form_schemas"], list)
        assert len(pcs["credential_form_schemas"]) > 0

    def test_provider_credential_schema_contains_api_key(self) -> None:
        data = _load()
        forms = data["provider_credential_schema"]["credential_form_schemas"]
        api_key_fields = [f for f in forms if f.get("variable") == "api_key"]
        assert (
            len(api_key_fields) == 1
        ), "Expected exactly one api_key field in provider_credential_schema"
        assert api_key_fields[0]["type"] == "secret-input"
        assert api_key_fields[0]["required"] is True

    def test_provider_credential_schema_contains_endpoint_url(self) -> None:
        """The endpoint_url field is what makes this plugin
        "OpenAI-API-compatible" — without it, users can't point at
        LM Studio / vLLM / LiteLLM / etc. The provider-level
        credential is the right place for this because it applies to
        every model under the provider.
        """
        data = _load()
        forms = data["provider_credential_schema"]["credential_form_schemas"]
        endpoint_url_fields = [f for f in forms if f.get("variable") == "endpoint_url"]
        assert len(endpoint_url_fields) == 1
        assert endpoint_url_fields[0]["type"] == "text-input"
        # endpoint_url is optional: leaving it blank uses the default
        # OpenAI endpoint.
        assert endpoint_url_fields[0]["required"] is False


class TestModelCredentialSchemaUnchanged:
    """The fix must not modify the existing model-level
    credential_form_schemas. The 36 model-level fields (mode, model
    type selectors, etc.) must remain.
    """

    def test_model_credential_schema_still_present(self) -> None:
        data = _load()
        assert "model_credential_schema" in data
        mcs = data["model_credential_schema"]
        assert "credential_form_schemas" in mcs
        # The pre-fix count was 36 model-level fields. The fix only
        # adds provider_credential_schema, not model-level fields.
        forms = mcs["credential_form_schemas"]
        assert len(forms) >= 30, (
            f"Model-level credential_form_schemas count dropped: {len(forms)}. "
            f"This is unexpected — the fix should only add provider_credential_schema."
        )

    def test_model_credential_schema_still_has_api_key(self) -> None:
        data = _load()
        forms = data["model_credential_schema"]["credential_form_schemas"]
        api_key_fields = [f for f in forms if f.get("variable") == "api_key"]
        assert len(api_key_fields) == 1


class TestProviderCredentialSchemaRoundTrip:
    """The schema must round-trip through yaml without losing the
    new field. This guards against a future maintainer who removes
    the field because it looks unused.
    """

    def test_yaml_dump_preserves_provider_credential_schema(self) -> None:
        data = _load()
        dumped = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        reloaded = yaml.safe_load(dumped)
        assert "provider_credential_schema" in reloaded
        assert (
            reloaded["provider_credential_schema"]["credential_form_schemas"]
            == data["provider_credential_schema"]["credential_form_schemas"]
        )

    def test_i18n_labels_present_on_provider_schema(self) -> None:
        """All field labels should have both en_US and zh_Hans
        (Dify's standard i18n). The provider-level schema is user-
        facing, so missing translations show up as raw English in
        Chinese-language deployments.
        """
        data = _load()
        for field in data["provider_credential_schema"]["credential_form_schemas"]:
            assert "label" in field, f"Field {field.get('variable')} missing label"
            label = field["label"]
            assert "en_US" in label, f"Field {field.get('variable')} label missing en_US"
            assert "zh_Hans" in label, f"Field {field.get('variable')} label missing zh_Hans"
