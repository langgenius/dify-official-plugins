"""Unit tests for the opt-in Dify metadata helper used by the OpenLLM plugin.

The helper writes Dify `X-Dify-App-Id` and `X-Dify-Source: dify` headers into
`credentials['extra_headers']` when the credential `enable_request_metadata` is
`"enabled"` and a Dify `app_id` resolves.

The OpenLLM plugin extends
``dify_plugin.interfaces.model.large_language_model.LargeLanguageModel``
directly (it does NOT use the OAICompatLargeLanguageModel base class).
The plugin issues ``requests.post(...)`` calls to the OpenLLM server with
a hand-built ``headers`` dict. The plugin's existing
``OpenLLMGenerate.generate(...)`` method accepts an ``extra_headers=``
kwarg which it merges into the outbound ``headers`` dict on every
request. The Dify app_id is propagated by writing the dify headers into
``credentials['extra_headers']`` before ``generate()`` runs and forwarding
them as the ``extra_headers=`` kwarg.

When the credential is disabled, or `app_id` is missing / empty, the helper
does nothing and the request shape is unchanged.

These tests do not need a network or the requests library: the helper is
pure and runs entirely in memory. The integration with
``OpenLLMLargeLanguageModel._generate`` is verified by the source-level
guard tests at the bottom of this file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

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
        "extra_headers": {"X-Custom-Header": "value"},
    }
    apply_dify_headers_if_enabled(credentials)
    assert credentials["extra_headers"] == {
        "X-Custom-Header": "value",
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
            "X-Custom-Header": "value",
        },
    }
    apply_dify_headers_if_enabled(credentials)
    assert credentials["extra_headers"] == {
        _APP_ID_HEADER: "app-123",
        _SOURCE_HEADER: _SOURCE_VALUE,
        "X-Custom-Header": "value",
    }


def test_enabled_does_not_mutate_caller_dict_reference() -> None:
    existing = {"X-Custom-Header": "value"}
    credentials = {
        "enable_request_metadata": _ENABLED,
        "app_id": "app-123",
        "extra_headers": existing,
    }
    apply_dify_headers_if_enabled(credentials)
    assert existing == {"X-Custom-Header": "value"}
    assert credentials["extra_headers"] is not existing
    assert credentials["extra_headers"] == {
        "X-Custom-Header": "value",
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
# Source-level guard
# ---------------------------------------------------------------------------


def test_helper_is_imported_and_used_in_llm() -> None:
    """The helper is wired into ``OpenLLMLargeLanguageModel._generate``.

    Note: OpenLLM extends
    ``dify_plugin.interfaces.model.large_language_model.LargeLanguageModel``
    directly (it does NOT use OAICompatLargeLanguageModel). The plugin
    issues ``requests.post(...)`` calls to the OpenLLM server with a
    hand-built ``headers`` dict (default: ``Content-Type`` +
    ``accept``). The plugin's existing
    ``OpenLLMGenerate.generate(...)`` method accepts an
    ``extra_headers=`` kwarg which it merges into the outbound
    ``headers`` dict on every request. The Dify app_id is propagated
    by writing the dify headers into ``credentials['extra_headers']``
    before ``generate()`` runs and forwarding them as the
    ``extra_headers=`` kwarg.

    The OpenLLM plugin also exposes a ``text_embedding`` module that
    uses a different code path and does NOT import the helper. The
    opt-in is scoped to the LLM endpoint only via
    ``show_on: - variable: __model_type, value: llm``.
    """
    llm_path = ROOT_DIR / "models" / "llm" / "llm.py"
    llm_source = llm_path.read_text(encoding="utf-8")
    assert "from ._metadata import apply_dify_headers_if_enabled" in llm_source
    assert "apply_dify_headers_if_enabled(credentials)" in llm_source
    # Helper is called exactly once (inside _generate).
    assert llm_source.count("apply_dify_headers_if_enabled(credentials)") == 1
    # The extra_headers= kwarg is forwarded to client.generate().
    assert 'extra_headers=credentials.get("extra_headers")' in llm_source
    # The base class is LargeLanguageModel (not OAICompat).
    assert "class OpenLLMLargeLanguageModel(LargeLanguageModel):" in llm_source


def test_helper_module_is_reachable_from_llm() -> None:
    helper_path = ROOT_DIR / "models" / "llm" / "_metadata.py"
    assert helper_path.is_file(), f"missing helper: {helper_path}"
    import models.llm._metadata as helper_module

    assert hasattr(helper_module, "apply_dify_headers_if_enabled")
    assert callable(helper_module.apply_dify_headers_if_enabled)
    assert hasattr(helper_module, "build_dify_headers")
    assert callable(helper_module.build_dify_headers)


def test_extra_headers_kwarg_added_to_openllm_generate() -> None:
    """Verify the ``extra_headers`` kwarg was added to ``OpenLLMGenerate.generate()``.

    This is the dispatch surface that the helper flows through: the
    plugin writes to ``credentials['extra_headers']`` and the SDK
    ``generate()`` method accepts the ``extra_headers=`` kwarg which
    it merges into the outbound ``headers`` dict before the
    ``requests.post()`` call.
    """
    import inspect

    from models.llm.openllm_generate import OpenLLMGenerate

    sig = inspect.signature(OpenLLMGenerate.generate)
    assert "extra_headers" in sig.parameters
    assert sig.parameters["extra_headers"].default is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-vv"]))
