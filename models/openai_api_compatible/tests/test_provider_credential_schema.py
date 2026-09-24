"""Regression test for #3682.

Configuring a credential for an OpenAI-API-compatible custom model in a
Knowledge Pipeline failed with "does not have
provider_credential_schema" -- the form could not render and the user
saw a red error toast. Dify requires every provider used in a Knowledge
Pipeline to declare a top-level ``provider_credential_schema`` so the
authorization form can render; the OpenAI-API-compatible plugin only
declared ``model_credential_schema``, so the provider-level schema
was missing.

These tests pin the shape of the new ``provider_credential_schema``
and the unchanged ``model_credential_schema`` so a future refactor
cannot accidentally drop the provider-level schema.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# Make the plugin importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


PROVIDER_YAML = (
    Path(__file__).resolve().parent.parent / "provider" / "openai_api_compatible.yaml"
)


@pytest.fixture(scope="module")
def provider_doc() -> dict:
    assert PROVIDER_YAML.exists(), f"missing provider yaml: {PROVIDER_YAML}"
    with PROVIDER_YAML.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_provider_yaml_declares_provider_credential_schema(provider_doc):
    """The whole point of #3682: provider_credential_schema must exist."""
    assert "provider_credential_schema" in provider_doc, (
        "OpenAI-API-compatible provider must declare provider_credential_schema "
        "so the Knowledge Pipeline authorization form can render. See #3682."
    )
    assert provider_doc["provider_credential_schema"] is not None


def test_provider_credential_form_has_api_key(provider_doc):
    """The two universal fields every OpenAI-compatible server needs:
    a bearer token and an optional endpoint URL.
    """
    form_schemas = provider_doc["provider_credential_schema"]["credential_form_schemas"]
    api_key_fields = [f for f in form_schemas if f.get("variable") == "api_key"]
    assert len(api_key_fields) == 1
    api_key = api_key_fields[0]
    assert api_key["type"] == "secret-input"
    assert api_key["required"] is True
    # The label is bilingual so the form renders in both en_US and zh_Hans.
    assert "en_US" in api_key["label"]
    assert "zh_Hans" in api_key["label"]


def test_provider_credential_form_has_optional_endpoint_url(provider_doc):
    """endpoint_url is optional so users on the default OpenAI endpoint
    don't have to set it. The credential form must accept an empty value."""
    form_schemas = provider_doc["provider_credential_schema"]["credential_form_schemas"]
    url_fields = [f for f in form_schemas if f.get("variable") == "endpoint_url"]
    assert len(url_fields) == 1
    url_field = url_fields[0]
    assert url_field["type"] == "text-input"
    assert url_field["required"] is False


def test_model_credential_schema_preserved(provider_doc):
    """Adding provider_credential_schema must not displace the
    per-model schema -- existing image/audio/llm/rerank/tts flows
    depend on it.
    """
    assert "model_credential_schema" in provider_doc
    model_schema = provider_doc["model_credential_schema"]
    # The model schema carries the same per-model credentials it did
    # before the fix; presence of the per-model "model" block is the
    # regression guard.
    assert "model" in model_schema
    assert "credential_form_schemas" in model_schema
    form_variables = {f["variable"] for f in model_schema["credential_form_schemas"]}
    # Spot-check a few of the per-model fields that have always been there.
    for required_field in ("api_key", "mode", "context_size"):
        assert required_field in form_variables, (
            f"model_credential_schema lost the {required_field!r} form field "
            f"in the provider_credential_schema refactor"
        )


def test_provider_yaml_round_trip():
    """YAML parses cleanly with PyYAML safe_load -- the credential
    schema must not introduce tags or other unsafe constructs.
    """
    with PROVIDER_YAML.open(encoding="utf-8") as f:
        raw = f.read()
    # A no-op round trip: parse then re-emit and re-parse. Catches
    # accidentally using !!python/str or other tags.
    first = yaml.safe_load(raw)
    second = yaml.safe_load(yaml.safe_dump(first, sort_keys=False))
    assert first == second
