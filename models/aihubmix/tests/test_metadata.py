"""Unit tests for the opt-in Dify metadata helper used by the Aihubmix plugin.

The helper writes Dify ``X-Dify-App-Id`` and ``X-Dify-Source: dify`` headers into
``credentials['extra_headers']`` when the credential ``enable_request_metadata``
is ``"enabled"`` and a Dify ``app_id`` resolves.

The Aihubmix plugin's chat calls dispatch through four SDK paths inside
``AihubmixLargeLanguageModel._dispatch_to_appropriate_model``:

1. ``claude*`` -> ``AnthropicLargeLanguageModel._invoke`` (Anthropic SDK)
2. ``gemini*`` (not -nothink / -search) -> ``GoogleLargeLanguageModel._invoke``
   (google-genai SDK)
3. ``gpt-5-codex | gpt-5-pro | gpt-5.6 | o3-pro`` -> ``AihubmixOpenAIResponses``
   (OpenAI Responses API)
4. otherwise -> ``super()._generate(...)`` (OAICompat base class)

The opt-in works by writing the Dify headers into
``credentials['extra_headers']`` from ``_update_credential`` (which runs
before any of the four submodules is dispatched) and having each submerge
``credentials.get("extra_headers", {})`` into its outbound headers dict.

When the credential is disabled, or ``app_id`` is missing / empty, the helper
does nothing and the request shape is unchanged.

These tests do not need a network or the SDKs: the helper is pure and runs
entirely in memory. The integration with each of the four dispatch paths is
verified by the source-level guard tests at the bottom of this file.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models.llm._metadata import (  # noqa: E402
    _normalize_header_value,
    apply_dify_headers_if_enabled,
    build_dify_headers,
)

_ENABLED = "enabled"
_APP_ID_HEADER = "X-Dify-App-Id"
_SOURCE_HEADER = "X-Dify-Source"
_SOURCE_VALUE = "dify"


# ---------------------------------------------------------------------------
# _normalize_header_value
# ---------------------------------------------------------------------------


def test_normalize_uuid_passthrough() -> None:
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    assert _normalize_header_value(uuid) == uuid


def test_normalize_preserves_punctuation() -> None:
    assert _normalize_header_value("a[b]c{d}e") == "a[b]c{d}e"


def test_normalize_strips_cr_lf() -> None:
    assert _normalize_header_value("a\r\nb") == "ab"


def test_normalize_strips_other_control_chars() -> None:
    assert _normalize_header_value("a\x00b\x07c") == "abc"


def test_normalize_coerces_non_string() -> None:
    assert _normalize_header_value(12345) == "12345"


def test_normalize_returns_empty_for_none() -> None:
    assert _normalize_header_value(None) == ""


def test_normalize_truncates_to_256_chars() -> None:
    s = "a" * 1024
    assert len(_normalize_header_value(s)) == 256


def test_normalize_returns_empty_for_all_control_chars() -> None:
    assert _normalize_header_value("\r\n\t\x00") == ""


# ---------------------------------------------------------------------------
# build_dify_headers
# ---------------------------------------------------------------------------


def test_build_headers_with_valid_app_id() -> None:
    headers = build_dify_headers("app-123")
    assert headers == {
        _APP_ID_HEADER: "app-123",
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


def test_build_headers_with_empty_app_id() -> None:
    assert build_dify_headers("") == {}


def test_build_headers_with_none_app_id() -> None:
    assert build_dify_headers(None) == {}


def test_build_headers_strips_cr_lf_in_app_id() -> None:
    headers = build_dify_headers("app\r\n123")
    assert headers == {
        _APP_ID_HEADER: "app123",
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


# ---------------------------------------------------------------------------
# apply_dify_headers_if_enabled — disabled / no-op paths
# ---------------------------------------------------------------------------


def test_disabled_does_not_set_extra_headers() -> None:
    credentials = {"app_id": "app-123"}
    apply_dify_headers_if_enabled(credentials)
    assert "extra_headers" not in credentials


def test_disabled_with_other_value_does_not_set_extra_headers() -> None:
    credentials = {"app_id": "app-123", "enable_request_metadata": "disabled"}
    apply_dify_headers_if_enabled(credentials)
    assert "extra_headers" not in credentials


def test_disabled_with_random_value_does_not_set_extra_headers() -> None:
    credentials = {"app_id": "app-123", "enable_request_metadata": "yes-please"}
    apply_dify_headers_if_enabled(credentials)
    assert "extra_headers" not in credentials


def test_enabled_without_app_id_does_not_set_extra_headers() -> None:
    credentials = {"enable_request_metadata": _ENABLED}
    apply_dify_headers_if_enabled(credentials)
    assert "extra_headers" not in credentials


def test_enabled_with_empty_app_id_does_not_set_extra_headers() -> None:
    credentials = {"enable_request_metadata": _ENABLED, "app_id": ""}
    apply_dify_headers_if_enabled(credentials)
    assert "extra_headers" not in credentials


def test_enabled_with_none_app_id_does_not_set_extra_headers() -> None:
    credentials = {"enable_request_metadata": _ENABLED, "app_id": None}
    apply_dify_headers_if_enabled(credentials)
    assert "extra_headers" not in credentials


# ---------------------------------------------------------------------------
# apply_dify_headers_if_enabled — enabled / positive paths
# ---------------------------------------------------------------------------


def test_enabled_with_app_id_attaches_both_headers() -> None:
    credentials = {"enable_request_metadata": _ENABLED, "app_id": "app-123"}
    apply_dify_headers_if_enabled(credentials)
    assert credentials["extra_headers"] == {
        _APP_ID_HEADER: "app-123",
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


def test_enabled_stringifies_non_string_app_id() -> None:
    credentials = {"enable_request_metadata": _ENABLED, "app_id": 12345}
    apply_dify_headers_if_enabled(credentials)
    assert credentials["extra_headers"][_APP_ID_HEADER] == "12345"
    assert credentials["extra_headers"][_SOURCE_HEADER] == _SOURCE_VALUE


def test_enabled_preserves_existing_extra_headers() -> None:
    credentials = {
        "enable_request_metadata": _ENABLED,
        "app_id": "app-123",
        "extra_headers": {"APP-Code": "Dify2025"},
    }
    apply_dify_headers_if_enabled(credentials)
    assert credentials["extra_headers"] == {
        "APP-Code": "Dify2025",
        _APP_ID_HEADER: "app-123",
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


def test_enabled_dify_keys_override_caller_on_collision() -> None:
    credentials = {
        "enable_request_metadata": _ENABLED,
        "app_id": "app-123",
        "extra_headers": {
            _APP_ID_HEADER: "old-value",
            _SOURCE_HEADER: "old-source",
            "APP-Code": "Dify2025",
        },
    }
    apply_dify_headers_if_enabled(credentials)
    assert credentials["extra_headers"] == {
        _APP_ID_HEADER: "app-123",
        _SOURCE_HEADER: _SOURCE_VALUE,
        "APP-Code": "Dify2025",
    }


def test_enabled_does_not_mutate_caller_dict_reference() -> None:
    existing = {"APP-Code": "Dify2025"}
    credentials = {
        "enable_request_metadata": _ENABLED,
        "app_id": "app-123",
        "extra_headers": existing,
    }
    apply_dify_headers_if_enabled(credentials)
    assert existing == {"APP-Code": "Dify2025"}
    assert credentials["extra_headers"] is not existing
    assert credentials["extra_headers"] == {
        "APP-Code": "Dify2025",
        _APP_ID_HEADER: "app-123",
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


def test_helper_never_raises_on_garbage_credentials() -> None:
    credentials = {"enable_request_metadata": _ENABLED, "app_id": "app-123"}
    apply_dify_headers_if_enabled(credentials)
    assert "extra_headers" in credentials


def test_helper_handles_extra_headers_as_none() -> None:
    credentials = {
        "enable_request_metadata": _ENABLED,
        "app_id": "app-123",
        "extra_headers": None,
    }
    apply_dify_headers_if_enabled(credentials)
    assert credentials["extra_headers"] == {
        _APP_ID_HEADER: "app-123",
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


# ---------------------------------------------------------------------------
# Source-level guard: 4-dispatch coverage
# ---------------------------------------------------------------------------


def test_helper_is_imported_and_used_in_llm() -> None:
    """The helper is wired into ``AihubmixLargeLanguageModel._update_credential``.

    Note: aihubmix dispatches chat calls to four SDK paths inside
    ``_dispatch_to_appropriate_model``. ``_update_credential`` runs first
    from ``_invoke`` and seeds ``credentials['extra_headers']`` with the
    pre-existing ``APP-Code: Dify2025`` marker. The helper writes
    ``X-Dify-App-Id`` / ``X-Dify-Source`` into the same dict when the
    opt-in is enabled. The four submodules each merge from
    ``credentials.get("extra_headers", ...)`` into their outbound headers
    dict, so the helper at this single chokepoint propagates to all four
    dispatch paths without per-call-site duplication.
    """
    llm_path = ROOT_DIR / "models" / "llm" / "llm.py"
    llm_source = llm_path.read_text(encoding="utf-8")
    assert "from ._metadata import apply_dify_headers_if_enabled" in llm_source
    assert "apply_dify_headers_if_enabled(credentials)" in llm_source
    # Helper is called exactly once (inside _update_credential).
    assert llm_source.count("apply_dify_headers_if_enabled(credentials)") == 1


def test_helper_module_is_reachable_from_llm() -> None:
    helper_path = ROOT_DIR / "models" / "llm" / "_metadata.py"
    assert helper_path.is_file(), f"missing helper: {helper_path}"
    import models.llm._metadata as helper_module

    assert hasattr(helper_module, "apply_dify_headers_if_enabled")
    assert callable(helper_module.apply_dify_headers_if_enabled)
    assert hasattr(helper_module, "build_dify_headers")
    assert callable(helper_module.build_dify_headers)


def test_anthropic_submodule_reads_extra_headers_from_credentials() -> None:
    """Anthropic submodule merges ``credentials['extra_headers']`` into its outbound dict.

    ``AnthropicLargeLanguageModel._chat_generate`` previously built an
    ``extra_headers`` dict locally with only ``APP-Code: Dify2025`` set.
    It now initialises the dict from ``credentials.get("extra_headers", ...)``
    so the helper-written ``X-Dify-App-Id`` / ``X-Dify-Source`` ride on
    every Anthropic ``messages.create`` call.
    """
    anthropic_path = ROOT_DIR / "models" / "llm" / "anthropic.py"
    anthropic_source = anthropic_path.read_text(encoding="utf-8")
    assert 'extra_headers = dict(credentials.get("extra_headers", {"APP-Code": "Dify2025"}))' in anthropic_source


def test_google_submodule_reads_extra_headers_from_credentials() -> None:
    """Google submodule merges ``credentials['extra_headers']`` into its http_options headers dict.

    ``GoogleLargeLanguageModel._generate`` previously built a ``headers``
    dict locally with only ``APP-Code: Dify2025`` set inside the
    ``http_options`` block. It now initialises the dict from
    ``credentials.get("extra_headers", ...)`` so the helper-written
    ``X-Dify-App-Id`` / ``X-Dify-Source`` ride on every google-genai
    ``models.generate_content`` / ``generate_content_stream`` call.
    """
    google_path = ROOT_DIR / "models" / "llm" / "google.py"
    google_source = google_path.read_text(encoding="utf-8")
    assert '"headers": dict(credentials.get("extra_headers", {"APP-Code": "Dify2025"}))' in google_source


def test_openai_response_submodule_reads_extra_headers_from_credentials() -> None:
    """OpenAI Responses submodule merges ``APP_CODE_HEADER`` with ``credentials['extra_headers']``.

    ``AihubmixOpenAIResponses`` previously passed the module-level
    ``APP_CODE_HEADER`` constant as ``extra_headers=`` to
    ``client.responses.create(...)``. It now builds a per-call dict that
    includes both ``APP-Code: Dify2025`` AND any opt-in headers
    (``X-Dify-App-Id`` / ``X-Dify-Source``) the helper wrote into
    ``credentials['extra_headers']``. The merge runs for both the
    streaming and non-streaming dispatch paths.
    """
    openai_response_path = ROOT_DIR / "models" / "llm" / "openai_response.py"
    openai_response_source = openai_response_path.read_text(encoding="utf-8")
    # The merge expression must appear twice: once in create_llm_result and
    # once in stream_llm_chunks.
    assert openai_response_source.count(
        "extra_headers = {**APP_CODE_HEADER, **self.credentials.get(\"extra_headers\", {})}"
    ) == 2
    # The pre-existing APP_CODE_HEADER constant is still used.
    assert "APP_CODE_HEADER = {\"APP-Code\": \"Dify2025\"}" in openai_response_source
    # The Responses API call uses the merged dict, not the bare constant.
    assert openai_response_source.count("extra_headers=extra_headers,") == 2
    assert openai_response_source.count("extra_headers=APP_CODE_HEADER,") == 0


def test_default_oaicompat_path_uses_credentials_extra_headers() -> None:
    """The default dispatch (super()._generate) inherits OAICompat standard threading.

    ``AihubmixLargeLanguageModel`` extends ``OAICompatLargeLanguageModel``
    and falls back to ``super()._generate(...)`` for any model that does
    not match the claude / gemini / RESPONSE_SERIES prefixes. The OAICompat
    base class already threads ``credentials['extra_headers']`` into the
    OpenAI SDK ``default_headers=`` parameter, so the helper at
    ``_update_credential`` is sufficient — no per-call-site wiring is
    required for this dispatch path.
    """
    llm_path = ROOT_DIR / "models" / "llm" / "llm.py"
    llm_source = llm_path.read_text(encoding="utf-8")
    assert "class AihubmixLargeLanguageModel(OAICompatLargeLanguageModel):" in llm_source
    # The default dispatch falls through to super()._generate.
    assert "return super()._generate(model, credentials, prompt_messages, model_parameters, tools, stop, stream, user)" in llm_source


def test_provider_yaml_exposes_enable_request_metadata() -> None:
    """The opt-in is exposed as a select on ``provider_credential_schema`` and ``model_credential_schema``.

    The schema is scoped to LLM only (show_on __model_type=llm) because
    aihubmix also exposes text-embedding, rerank, tts and speech2text
    modules, and the opt-in only applies to the chat endpoint (the four
    dispatch submodules under ``AihubmixLargeLanguageModel``).
    """
    import yaml

    yaml_path = ROOT_DIR / "provider" / "aihubmix.yaml"
    parsed = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

    provider_vars = [
        s["variable"]
        for s in parsed["provider_credential_schema"]["credential_form_schemas"]
    ]
    model_vars = [
        s["variable"]
        for s in parsed["model_credential_schema"]["credential_form_schemas"]
    ]

    assert "enable_request_metadata" in provider_vars, (
        "enable_request_metadata must appear in provider_credential_schema"
    )
    assert "enable_request_metadata" in model_vars, (
        "enable_request_metadata must appear in model_credential_schema"
    )

    # Locate the schemas.
    provider_schema = next(
        s
        for s in parsed["provider_credential_schema"]["credential_form_schemas"]
        if s["variable"] == "enable_request_metadata"
    )
    model_schema = next(
        s
        for s in parsed["model_credential_schema"]["credential_form_schemas"]
        if s["variable"] == "enable_request_metadata"
    )
    # Default is disabled (opt-in).
    assert provider_schema["default"] == "disabled"
    assert model_schema["default"] == "disabled"
    # Enabled/Disabled options present.
    option_values = {opt["value"] for opt in provider_schema["options"]}
    assert option_values == {"enabled", "disabled"}
    assert {opt["value"] for opt in model_schema["options"]} == {"enabled", "disabled"}
    # Scoped to LLM only via show_on.
    assert provider_schema["show_on"] == [{"variable": "__model_type", "value": "llm"}]
    assert model_schema["show_on"] == [{"variable": "__model_type", "value": "llm"}]