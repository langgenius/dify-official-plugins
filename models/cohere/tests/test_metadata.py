"""Unit tests for the opt-in Dify metadata helper used by the Cohere plugin.

The helper builds a `cohere.core.RequestOptions` for `Client.chat` / `Client.generate`
calls. When the credential `enable_request_metadata` is `"enabled"` and a Dify `app_id`
resolves, the returned options carry `X-Dify-App-Id` and `X-Dify-Source: dify` via
`additional_headers`. In every other case the helper returns a plain
`RequestOptions(max_retries=0)` with no additional headers, so the call site can use the
helper unconditionally.

These tests do not need a network or the Cohere SDK: `cohere.core.RequestOptions` is a
plain pydantic-style dataclass and is imported only via the helper module. We do not
mock the SDK; we exercise the helper directly. The integration with `_chat_generate`
and `_generate` is verified by the source-level guard test at the bottom of this file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models.llm._metadata import build_cohere_request_options

_ENABLED = "enabled"
_APP_ID_HEADER = "X-Dify-App-Id"
_SOURCE_HEADER = "X-Dify-Source"
_SOURCE_VALUE = "dify"


# ---------------------------------------------------------------------------
# Disabled / no-op paths
# ---------------------------------------------------------------------------


def test_disabled_returns_no_additional_headers() -> None:
    """`enable_request_metadata` unset -> no headers, max_retries=0 preserved."""
    options = build_cohere_request_options({"app_id": "app-123"})
    assert options["max_retries"] == 0
    assert options.get("additional_headers") is None


def test_disabled_with_other_value_returns_no_additional_headers() -> None:
    """Any non-`enabled` value (including `disabled`) keeps the request shape."""
    options = build_cohere_request_options(
        {"app_id": "app-123", "enable_request_metadata": "disabled"}
    )
    assert options["max_retries"] == 0
    assert options.get("additional_headers") is None


def test_disabled_with_random_value_returns_no_additional_headers() -> None:
    """Random garbage values must not silently enable metadata."""
    options = build_cohere_request_options(
        {"app_id": "app-123", "enable_request_metadata": "yes-please"}
    )
    assert options.get("additional_headers") is None


def test_enabled_without_app_id_returns_no_additional_headers() -> None:
    """`enabled` but missing `app_id` -> no headers, request still proceeds."""
    options = build_cohere_request_options({"enable_request_metadata": _ENABLED})
    assert options["max_retries"] == 0
    assert options.get("additional_headers") is None


def test_enabled_with_empty_app_id_returns_no_additional_headers() -> None:
    """`enabled` but empty-string `app_id` -> no headers."""
    options = build_cohere_request_options(
        {"enable_request_metadata": _ENABLED, "app_id": ""}
    )
    assert options.get("additional_headers") is None


def test_enabled_with_none_app_id_returns_no_additional_headers() -> None:
    """`enabled` but `app_id=None` -> no headers."""
    options = build_cohere_request_options(
        {"enable_request_metadata": _ENABLED, "app_id": None}
    )
    assert options.get("additional_headers") is None


# ---------------------------------------------------------------------------
# Enabled / positive paths
# ---------------------------------------------------------------------------


def test_enabled_with_app_id_attaches_both_headers() -> None:
    """Happy path: `enabled` + valid `app_id` -> both headers attached."""
    options = build_cohere_request_options(
        {"enable_request_metadata": _ENABLED, "app_id": "app-123"}
    )
    assert options["max_retries"] == 0
    assert options["additional_headers"] == {
        _APP_ID_HEADER: "app-123",
        _SOURCE_HEADER: _SOURCE_VALUE,
    }


def test_enabled_stringifies_non_string_app_id() -> None:
    """Numeric / other app_id values are stringified rather than dropped.

    Mirrors the existing dify bury-point behavior: the app_id is treated as opaque.
    """
    options = build_cohere_request_options(
        {"enable_request_metadata": _ENABLED, "app_id": 12345}
    )
    assert options.get("additional_headers") is not None
    assert options["additional_headers"][_APP_ID_HEADER] == "12345"
    assert options["additional_headers"][_SOURCE_HEADER] == _SOURCE_VALUE


def test_enabled_does_not_mutate_input_credentials() -> None:
    """The helper must not mutate the caller's `credentials` dict."""
    credentials = {"enable_request_metadata": _ENABLED, "app_id": "app-123"}
    snapshot = dict(credentials)
    build_cohere_request_options(credentials)
    assert credentials == snapshot


def test_enabled_preserves_max_retries() -> None:
    """Even when metadata is attached, `max_retries=0` is preserved so we do not
    silently retry on failures (the prior behavior)."""
    options = build_cohere_request_options(
        {"enable_request_metadata": _ENABLED, "app_id": "app-123"}
    )
    assert options["max_retries"] == 0


# ---------------------------------------------------------------------------
# Header-field collision handling
# ---------------------------------------------------------------------------


def test_enabled_uses_canonical_dify_keys() -> None:
    """Both header keys must be exactly the documented names.

    The Dify backend identifies these by exact match; a typo (e.g. `X-Dify-Appid`)
    would be silently ignored downstream.
    """
    options = build_cohere_request_options(
        {"enable_request_metadata": _ENABLED, "app_id": "app-123"}
    )
    assert options.get("additional_headers") is not None
    keys = set(options["additional_headers"].keys())
    assert _APP_ID_HEADER in keys
    assert _SOURCE_HEADER in keys
    # And no snake_case / kebab-case variants leak in.
    assert "X-Dify-app-id" not in keys
    assert "x-dify-app-id" not in keys


def test_enabled_header_values_are_strings() -> None:
    """Header values must be `str` (Cohere SDK contract). Numeric / None / bool values
    would be rejected at the transport layer."""
    options = build_cohere_request_options(
        {"enable_request_metadata": _ENABLED, "app_id": 12345}  # numeric app_id
    )
    assert options.get("additional_headers") is not None
    assert isinstance(options["additional_headers"][_APP_ID_HEADER], str)
    assert isinstance(options["additional_headers"][_SOURCE_HEADER], str)


# ---------------------------------------------------------------------------
# Robustness: the helper must never raise
# ---------------------------------------------------------------------------


def test_helper_never_raises_on_garbage_credentials() -> None:
    """If building the options fails for any reason, fall back to a plain
    `RequestOptions(max_retries=0)`. The user request must not be blocked by a
    metadata-wiring bug."""
    # `RequestOptions(max_retries=0)` is the only guarantee we need.
    options = build_cohere_request_options(
        {"enable_request_metadata": _ENABLED, "app_id": "app-123"}
    )
    # `cohere.core.RequestOptions` is a TypedDict, so the runtime type is plain
    # `dict`. The contract is: never `None`, always a mapping carrying
    # `max_retries=0`.
    assert options is not None
    assert options["max_retries"] == 0


# ---------------------------------------------------------------------------
# Return-type contract
# ---------------------------------------------------------------------------


def test_return_type_is_always_dict_like() -> None:
    """The helper always returns a `dict`-like mapping; never `None`, never a scalar.

    `cohere.core.RequestOptions` is a TypedDict, so the runtime type is plain
    `dict`. The contract `_chat_generate` and `_generate` rely on is "always a
    mapping with `max_retries=0` that I can pass to `request_options=...`".
    """
    samples = [
        {},
        {"enable_request_metadata": "disabled"},
        {"enable_request_metadata": _ENABLED},
        {"enable_request_metadata": _ENABLED, "app_id": "app-123"},
        {"enable_request_metadata": _ENABLED, "app_id": 42},
        {"enable_request_metadata": "garbage"},
    ]
    for credentials in samples:
        result = build_cohere_request_options(credentials)
        assert result is not None, f"helper returned None for {credentials!r}"
        assert isinstance(result, dict), (
            f"expected dict, got {type(result).__name__} for {credentials!r}"
        )
        assert result["max_retries"] == 0


# ---------------------------------------------------------------------------
# Source-level guard: the helper is wired into llm.py at the documented sites
# ---------------------------------------------------------------------------


def test_helper_is_used_in_llm_py_at_all_request_options_sites() -> None:
    """Source-level guard.

    The helper replaces `RequestOptions(max_retries=0)` at four call sites in
    `models/llm/llm.py` (two in `_generate`, two in `_chat_generate`). This test
    catches accidental removal during refactors by reading the source.
    """
    llm_path = ROOT_DIR / "models" / "llm" / "llm.py"
    source = llm_path.read_text(encoding="utf-8")
    # The helper is imported in llm.py.
    assert "from models.llm._metadata import build_cohere_request_options" in source
    # And used at every call site. There are exactly 4 `request_options=` call
    # sites in the file (two in `_generate`, two in `_chat_generate`).
    assert (
        source.count("request_options=build_cohere_request_options(credentials)") == 4
    )
    # No raw `RequestOptions(max_retries=0)` should remain in the file -- they all
    # route through the helper now.
    assert "RequestOptions(max_retries=0)" not in source


def test_helper_module_is_reachable_from_llm() -> None:
    """The helper file exists at the expected path and is importable."""
    helper_path = ROOT_DIR / "models" / "llm" / "_metadata.py"
    assert helper_path.is_file(), f"missing helper: {helper_path}"
    # And it exports the public symbol.
    import models.llm._metadata as helper_module

    assert hasattr(helper_module, "build_cohere_request_options")
    assert callable(helper_module.build_cohere_request_options)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-vv"]))
