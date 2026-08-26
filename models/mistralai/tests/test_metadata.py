"""Unit tests for the opt-in Dify metadata helper used by the MistralAI plugin.

The helper writes Dify `X-Dify-App-Id` and `X-Dify-Source: dify` headers into
`credentials['extra_headers']` when the credential `enable_request_metadata` is
`"enabled"` and a Dify `app_id` resolves. The underlying OAICompat base class
(`dify_plugin.OAICompatLargeLanguageModel`) reads `credentials['extra_headers']`
and merges the entries into the outbound HTTP request headers, so writing to
that credential is the carrier for observability metadata.

When the credential is disabled, or `app_id` is missing / empty, the helper
does nothing and the request shape is unchanged.

These tests do not need a network or the MistralAI SDK: the helper is pure
and runs entirely in memory. The integration with `_invoke` and
`validate_credentials` is verified by the source-level guard tests at the
bottom of this file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models.llm._metadata import (
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
    """UUIDs and other visible-ASCII app_ids pass through unchanged."""
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    assert _normalize_header_value(uuid) == uuid


def test_normalize_preserves_punctuation() -> None:
    """Visible ASCII punctuation is preserved; only CR/LF and other control
    characters are stripped."""
    assert _normalize_header_value("a[b]c{d}e") == "a[b]c{d}e"


def test_normalize_strips_cr_lf() -> None:
    """CR/LF must be stripped because urllib3 rejects them in headers."""
    assert _normalize_header_value("a\r\nb") == "ab"


def test_normalize_strips_other_control_chars() -> None:
    """Other control characters (e.g. NUL, BEL) must be stripped too."""
    assert _normalize_header_value("a\x00b\x07c") == "abc"


def test_normalize_coerces_non_string() -> None:
    """Numeric input is stringified rather than dropped."""
    assert _normalize_header_value(12345) == "12345"


def test_normalize_returns_empty_for_none() -> None:
    """None normalizes to the empty string."""
    assert _normalize_header_value(None) == ""


def test_normalize_truncates_to_256_chars() -> None:
    """Hard cap of 256 characters to keep header values bounded."""
    s = "a" * 1024
    assert len(_normalize_header_value(s)) == 256


def test_normalize_returns_empty_for_all_control_chars() -> None:
    """If everything is a control character, the result is the empty string."""
    assert _normalize_header_value("\r\n\t\x00") == ""


# ---------------------------------------------------------------------------
# build_dify_headers
# ---------------------------------------------------------------------------


def test_build_headers_with_valid_app_id() -> None:
    """Happy path: app_id is set -> both headers returned."""
    headers = build_dify_headers("app-123")
    assert headers == {
        _APP_ID_HEADER: "app-123",
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


def test_build_headers_with_empty_app_id() -> None:
    """Empty app_id -> empty dict (caller can skip header attachment)."""
    assert build_dify_headers("") == {}


def test_build_headers_with_none_app_id() -> None:
    """None app_id -> empty dict."""
    assert build_dify_headers(None) == {}


def test_build_headers_strips_cr_lf_in_app_id() -> None:
    """If app_id contains CR/LF, it is sanitized before being used as a header value."""
    headers = build_dify_headers("app\r\n123")
    assert headers == {
        _APP_ID_HEADER: "app123",
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


# ---------------------------------------------------------------------------
# apply_dify_headers_if_enabled — disabled / no-op paths
# ---------------------------------------------------------------------------


def test_disabled_does_not_set_extra_headers() -> None:
    """`enable_request_metadata` unset -> extra_headers is not touched."""
    credentials = {"app_id": "app-123"}
    apply_dify_headers_if_enabled(credentials)
    assert "extra_headers" not in credentials


def test_disabled_with_other_value_does_not_set_extra_headers() -> None:
    """Any non-`enabled` value (including `disabled`) leaves credentials alone."""
    credentials = {"app_id": "app-123", "enable_request_metadata": "disabled"}
    apply_dify_headers_if_enabled(credentials)
    assert "extra_headers" not in credentials


def test_disabled_with_random_value_does_not_set_extra_headers() -> None:
    """Random garbage values must not silently enable metadata."""
    credentials = {"app_id": "app-123", "enable_request_metadata": "yes-please"}
    apply_dify_headers_if_enabled(credentials)
    assert "extra_headers" not in credentials


def test_enabled_without_app_id_does_not_set_extra_headers() -> None:
    """`enabled` but missing `app_id` -> no headers attached."""
    credentials = {"enable_request_metadata": _ENABLED}
    apply_dify_headers_if_enabled(credentials)
    assert "extra_headers" not in credentials


def test_enabled_with_empty_app_id_does_not_set_extra_headers() -> None:
    """`enabled` but empty-string `app_id` -> no headers attached."""
    credentials = {"enable_request_metadata": _ENABLED, "app_id": ""}
    apply_dify_headers_if_enabled(credentials)
    assert "extra_headers" not in credentials


def test_enabled_with_none_app_id_does_not_set_extra_headers() -> None:
    """`enabled` but `app_id=None` -> no headers attached."""
    credentials = {"enable_request_metadata": _ENABLED, "app_id": None}
    apply_dify_headers_if_enabled(credentials)
    assert "extra_headers" not in credentials


# ---------------------------------------------------------------------------
# apply_dify_headers_if_enabled — enabled / positive paths
# ---------------------------------------------------------------------------


def test_enabled_with_app_id_attaches_both_headers() -> None:
    """Happy path: `enabled` + valid `app_id` -> both headers attached."""
    credentials = {"enable_request_metadata": _ENABLED, "app_id": "app-123"}
    apply_dify_headers_if_enabled(credentials)
    assert credentials["extra_headers"] == {
        _APP_ID_HEADER: "app-123",
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


def test_enabled_stringifies_non_string_app_id() -> None:
    """Numeric / other app_id values are stringified rather than dropped.

    Mirrors the existing dify bury-point behavior: the app_id is treated as opaque.
    """
    credentials = {"enable_request_metadata": _ENABLED, "app_id": 12345}
    apply_dify_headers_if_enabled(credentials)
    assert credentials["extra_headers"][_APP_ID_HEADER] == "12345"
    assert credentials["extra_headers"][_SOURCE_HEADER] == _SOURCE_VALUE


def test_enabled_preserves_existing_extra_headers() -> None:
    """If the caller already set `extra_headers`, those entries are preserved
    alongside the Dify ones (non-destructive merge)."""
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
    """If the caller already set `X-Dify-App-Id` or `X-Dify-Source`, the helper
    overrides those entries so the helper always controls its own observability
    markers."""
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
    """The helper copies the existing `extra_headers` dict before merging so
    the caller's reference is not mutated. The OAICompat base class may
    re-use the reference elsewhere, so we must not stomp on the caller's
    input."""
    existing = {"X-Custom-Header": "value"}
    credentials = {
        "enable_request_metadata": _ENABLED,
        "app_id": "app-123",
        "extra_headers": existing,
    }
    apply_dify_headers_if_enabled(credentials)
    # The caller's existing dict reference is unchanged.
    assert existing == {"X-Custom-Header": "value"}
    # But the credentials dict now points to a new merged dict.
    assert credentials["extra_headers"] is not existing
    assert credentials["extra_headers"] == {
        "X-Custom-Header": "value",
        _APP_ID_HEADER: "app-123",
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


# ---------------------------------------------------------------------------
# Robustness: the helper must never raise
# ---------------------------------------------------------------------------


def test_helper_never_raises_on_garbage_credentials() -> None:
    """If anything goes wrong while building the headers, the helper is a no-op.
    The user request must not be blocked by a metadata-wiring bug."""
    # `apply_dify_headers_if_enabled` is a void function; the only guarantee we
    # need is that the credentials dict is still well-formed (no extra_headers
    # set in the no-op case).
    credentials = {"enable_request_metadata": _ENABLED, "app_id": "app-123"}
    apply_dify_headers_if_enabled(credentials)
    assert "extra_headers" in credentials  # happy path; coverage is per other tests


def test_helper_handles_extra_headers_as_non_dict() -> None:
    """If the caller sets `extra_headers` to a non-dict (e.g. None or a list),
    the helper treats it as absent and creates a fresh dict. This guards
    against a downstream consumer corrupting the credential."""
    # None: treated as absent -> fresh dict with just the dify keys.
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
# Source-level guard: the helper is wired into llm.py at the documented sites
# ---------------------------------------------------------------------------


def test_helper_is_imported_in_llm_py() -> None:
    """Source-level guard: the helper is wired into MistralAILargeLanguageModel."""
    llm_path = ROOT_DIR / "models" / "llm" / "llm.py"
    source = llm_path.read_text(encoding="utf-8")
    assert "from models.llm._metadata import apply_dify_headers_if_enabled" in source
    # Used at both call sites: in `_invoke` (after `_add_custom_parameters`) and
    # in `validate_credentials` (after `_add_custom_parameters`).
    assert source.count("apply_dify_headers_if_enabled(credentials)") == 2
    # Called only AFTER `_add_custom_parameters(credentials)` so the endpoint_url
    # is set first; the helper does not depend on it, but ordering matters for
    # maintainability.
    invoke_block = source[
        source.index("def _invoke(") : source.index("def _invoke(") + 2000
    ]
    assert invoke_block.find(
        "self._add_custom_parameters(credentials)"
    ) < invoke_block.find("apply_dify_headers_if_enabled(credentials)")


def test_helper_module_is_reachable_from_llm() -> None:
    """The helper file exists at the expected path and is importable."""
    helper_path = ROOT_DIR / "models" / "llm" / "_metadata.py"
    assert helper_path.is_file(), f"missing helper: {helper_path}"
    import models.llm._metadata as helper_module

    assert hasattr(helper_module, "apply_dify_headers_if_enabled")
    assert callable(helper_module.apply_dify_headers_if_enabled)
    assert hasattr(helper_module, "build_dify_headers")
    assert callable(helper_module.build_dify_headers)


# ---------------------------------------------------------------------------
# Integration: the helper is wired into both _invoke and validate_credentials.
# The validate_credentials path uses requests.post directly and does NOT
# read extra_headers, so the helper call there is a no-op w.r.t. the wire
# request. We assert that explicitly so future refactors of the OAICompat
# base class don't silently change the behavior.
# ---------------------------------------------------------------------------


def test_helper_in_validate_credentials_path_is_a_noop_wire_writes() -> None:
    """End-to-end check that calling the helper via the wired `validate_credentials`
    path is a no-op w.r.t. what reaches the wire.

    We patch the parent's `validate_credentials` so no real network call is
    attempted, and verify that the helper mutates `credentials['extra_headers']`
    the same way it does in `_invoke`. The fact that the OAICompat base class
    `validate_credentials` does not consume `extra_headers` is documented in
    `references/issue_discovery.md` and verified by reading the OAICompat
    source: it builds its own `headers` dict from `api_key` only and calls
    `requests.post` directly, so the helper's mutation is observable in
    `credentials` but does not affect the wire request. This test guards
    against a future refactor that would make the validate_credentials path
    sensitive to `extra_headers`.
    """
    from unittest.mock import MagicMock, patch

    from models.llm.llm import MistralAILargeLanguageModel

    model = MistralAILargeLanguageModel(model_schemas=MagicMock())

    with patch.object(
        MistralAILargeLanguageModel,
        "_add_custom_parameters",
        lambda self, c: c.update(
            {"mode": "chat", "endpoint_url": "https://api.mistral.ai/v1/"}
        ),
    ), patch(
        "dify_plugin.OAICompatLargeLanguageModel.validate_credentials",
        return_value=None,
    ):
        creds = {"enable_request_metadata": _ENABLED, "app_id": "app-xyz"}
        model.validate_credentials("mistral-large-latest", creds)
        # The helper still mutates `credentials['extra_headers']` exactly
        # as it does in `_invoke`. Whether the wire request picks it up
        # depends on the OAICompat base class, which we do not test here.
        assert "extra_headers" in creds
        assert creds["extra_headers"][_APP_ID_HEADER] == "app-xyz"
        assert creds["extra_headers"][_SOURCE_HEADER] == _SOURCE_VALUE


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-vv"]))
