"""Regression coverage for issue #3682.

Dify's Knowledge Pipeline flow requires every provider used there to
declare a top-level ``provider_credential_schema`` so the credential
authorization form can render. The OpenAI-API-compatible plugin only
declared ``model_credential_schema``; the provider-level schema was
missing and the form failed with "does not have
provider_credential_schema" when the user wired a custom model into a
Knowledge Pipeline.

These tests pin the provider credential schema in place so the bug
cannot regress.
"""

from __future__ import annotations

from pathlib import Path

import yaml

PROVIDER_YAML = (
    Path(__file__).resolve().parent.parent / "provider" / "openai_api_compatible.yaml"
)


def _load_provider_yaml() -> dict:
    with PROVIDER_YAML.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_provider_credential_schema_is_declared():
    data = _load_provider_yaml()
    assert "provider_credential_schema" in data, (
        "Knowledge Pipeline credential setup needs a top-level "
        "provider_credential_schema (see issue #3682)."
    )


def test_provider_credential_schema_uses_documented_form_shape():
    data = _load_provider_yaml()
    schema = data["provider_credential_schema"]
    assert "credential_form_schemas" in schema
    assert isinstance(schema["credential_form_schemas"], list)
    assert schema["credential_form_schemas"]


def test_api_key_field_is_required_secret_input():
    data = _load_provider_yaml()
    fields = {
        field["variable"]: field
        for field in data["provider_credential_schema"]["credential_form_schemas"]
    }
    assert "api_key" in fields
    api_key = fields["api_key"]
    assert api_key["type"] == "secret-input"
    assert api_key["required"] is True
    assert "en_US" in api_key["label"]
    assert "zh_Hans" in api_key["label"]


def test_endpoint_url_field_is_optional_text_input():
    data = _load_provider_yaml()
    fields = {
        field["variable"]: field
        for field in data["provider_credential_schema"]["credential_form_schemas"]
    }
    assert "endpoint_url" in fields
    endpoint = fields["endpoint_url"]
    assert endpoint["type"] == "text-input"
    assert endpoint["required"] is False
    assert "en_US" in endpoint["label"]
    assert "zh_Hans" in endpoint["label"]


def test_model_credential_schema_remains_unchanged():
    """The fix is strictly additive: per-model credential fields stay."""
    data = _load_provider_yaml()
    assert "model_credential_schema" in data
    model_fields = data["model_credential_schema"].get("credential_form_schemas", [])
    assert len(model_fields) >= 30, (
        "Per-model credential form schema should keep its 30+ fields; "
        "regression would break existing custom-model configuration flows."
    )
    variables = {field["variable"] for field in model_fields}
    assert "api_key" in variables
    assert "endpoint_url" in variables


def test_provider_credential_schema_yaml_round_trips():
    """The new field survives a yaml round-trip without loss."""
    data = _load_provider_yaml()
    reserialized = yaml.safe_load(yaml.safe_dump(data, allow_unicode=True))
    assert (
        reserialized["provider_credential_schema"] == data["provider_credential_schema"]
    )
