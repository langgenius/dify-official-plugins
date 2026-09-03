"""Unit tests for the opt-in Dify metadata helper used by the SageMaker plugin.

The helper writes a `dify_app_id` and `dify_source` keys into
`credentials['_dify_metadata']` when the credential `enable_request_metadata`
is `"enabled"` and a Dify `app_id` resolves (via
`dify_plugin.get_current_session()`). The `inference` function then
merges this dict into the SageMaker request payload as
`payload['_dify_metadata']`.

When the credential is disabled, or `app_id` is missing / empty, the
helper does nothing and the request shape is unchanged.

These tests do not need a network or the SageMaker SDK: the helper is
pure and runs entirely in memory. The integration with `inference` and
`_invoke` is verified by the source-level guard tests at the bottom of
this file.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models.llm._metadata import (
    _normalize_metadata_value,
    apply_dify_metadata_if_enabled,
    build_dify_metadata,
)

_ENABLED = "enabled"
_METADATA_KEY = "_dify_metadata"
_APP_ID_KEY = "dify_app_id"
_SOURCE_KEY = "dify_source"
_SOURCE_VALUE = "dify"


# ---------------------------------------------------------------------------
# _normalize_metadata_value
# ---------------------------------------------------------------------------


def test_normalize_uuid_passthrough() -> None:
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    assert _normalize_metadata_value(uuid) == uuid


def test_normalize_preserves_punctuation() -> None:
    assert _normalize_metadata_value("a[b]c{d}e") == "a[b]c{d}e"


def test_normalize_coerces_non_string() -> None:
    assert _normalize_metadata_value(12345) == "12345"


def test_normalize_returns_empty_for_none() -> None:
    assert _normalize_metadata_value(None) == ""


def test_normalize_returns_empty_for_empty_string() -> None:
    assert _normalize_metadata_value("") == ""


def test_normalize_truncates_to_256_chars() -> None:
    s = "a" * 1024
    assert len(_normalize_metadata_value(s)) == 256


# ---------------------------------------------------------------------------
# build_dify_metadata
# ---------------------------------------------------------------------------


def test_build_metadata_with_valid_app_id() -> None:
    metadata = build_dify_metadata("app-123")
    assert metadata == {
        _APP_ID_KEY: "app-123",
        _SOURCE_KEY: _SOURCE_VALUE,
    }


def test_build_metadata_with_empty_app_id() -> None:
    assert build_dify_metadata("") is None


def test_build_metadata_with_none_app_id() -> None:
    assert build_dify_metadata(None) is None


def test_build_metadata_truncates_long_app_id() -> None:
    long_id = "a" * 1024
    metadata = build_dify_metadata(long_id)
    assert metadata is not None
    assert len(metadata[_APP_ID_KEY]) == 256


# ---------------------------------------------------------------------------
# apply_dify_metadata_if_enabled — disabled / no-op paths
# ---------------------------------------------------------------------------


def test_disabled_returns_without_setting_metadata() -> None:
    credentials: dict = {}
    apply_dify_metadata_if_enabled(credentials)
    assert _METADATA_KEY not in credentials


def test_disabled_with_other_value_returns_without_setting_metadata() -> None:
    credentials: dict = {"enable_request_metadata": "disabled"}
    apply_dify_metadata_if_enabled(credentials)
    assert _METADATA_KEY not in credentials


def test_disabled_with_random_value_returns_without_setting_metadata() -> None:
    credentials: dict = {"enable_request_metadata": "yes-please"}
    apply_dify_metadata_if_enabled(credentials)
    assert _METADATA_KEY not in credentials


def test_enabled_without_app_id_returns_without_setting_metadata() -> None:
    credentials: dict = {"enable_request_metadata": _ENABLED}
    apply_dify_metadata_if_enabled(credentials)
    assert _METADATA_KEY not in credentials


def test_enabled_with_empty_app_id_returns_without_setting_metadata() -> None:
    credentials: dict = {"enable_request_metadata": _ENABLED, "app_id": ""}
    apply_dify_metadata_if_enabled(credentials)
    assert _METADATA_KEY not in credentials


# ---------------------------------------------------------------------------
# apply_dify_metadata_if_enabled — enabled / positive paths (with monkeypatched
# dify_plugin.get_current_session)
# ---------------------------------------------------------------------------


def test_enabled_with_app_id_sets_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: `enabled` + valid app_id -> credentials[_dify_metadata] is set."""
    import dify_plugin

    fake_session = SimpleNamespace(app_id="app-123")
    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: fake_session)

    credentials: dict = {"enable_request_metadata": _ENABLED}
    apply_dify_metadata_if_enabled(credentials)
    assert credentials[_METADATA_KEY] == {
        _APP_ID_KEY: "app-123",
        _SOURCE_KEY: _SOURCE_VALUE,
    }


def test_enabled_overwrites_existing_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If `credentials[_dify_metadata]` is already set, the helper overwrites it
    so the helper always controls its own observability markers."""
    import dify_plugin

    fake_session = SimpleNamespace(app_id="app-123")
    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: fake_session)

    credentials: dict = {
        "enable_request_metadata": _ENABLED,
        _METADATA_KEY: {_APP_ID_KEY: "old-value", _SOURCE_KEY: "old-source"},
    }
    apply_dify_metadata_if_enabled(credentials)
    assert credentials[_METADATA_KEY] == {
        _APP_ID_KEY: "app-123",
        _SOURCE_KEY: _SOURCE_VALUE,
    }


def test_enabled_stringifies_non_string_app_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Numeric / other app_id values are stringified rather than dropped."""
    import dify_plugin

    fake_session = SimpleNamespace(app_id=12345)
    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: fake_session)

    credentials: dict = {"enable_request_metadata": _ENABLED}
    apply_dify_metadata_if_enabled(credentials)
    assert credentials[_METADATA_KEY][_APP_ID_KEY] == "12345"
    assert credentials[_METADATA_KEY][_SOURCE_KEY] == _SOURCE_VALUE


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


def test_helper_never_raises_on_session_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If `get_current_session` raises, the helper is a no-op (no mutation)."""
    import dify_plugin

    def _raising():
        raise RuntimeError("session not available")

    monkeypatch.setattr(dify_plugin, "get_current_session", _raising)

    credentials: dict = {"enable_request_metadata": _ENABLED}
    apply_dify_metadata_if_enabled(credentials)
    assert _METADATA_KEY not in credentials


def test_helper_never_raises_on_session_returning_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If `get_current_session` returns None, the helper is a no-op (no mutation)."""
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: None)

    credentials: dict = {"enable_request_metadata": _ENABLED}
    apply_dify_metadata_if_enabled(credentials)
    assert _METADATA_KEY not in credentials


def test_helper_never_raises_on_session_without_app_id_attr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the session object has no `app_id` attribute, the helper is a no-op."""
    import dify_plugin

    fake_session = SimpleNamespace()  # no app_id attribute
    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: fake_session)

    credentials: dict = {"enable_request_metadata": _ENABLED}
    apply_dify_metadata_if_enabled(credentials)
    assert _METADATA_KEY not in credentials


# ---------------------------------------------------------------------------
# Source-level guard
# ---------------------------------------------------------------------------


def test_helper_is_imported_in_llm_py() -> None:
    """The helper is wired into SageMakerLargeLanguageModel."""
    llm_path = ROOT_DIR / "models" / "llm" / "llm.py"
    source = llm_path.read_text(encoding="utf-8")
    assert "from models.llm._metadata import apply_dify_metadata_if_enabled" in source
    # Helper is called in both `_invoke` and `validate_credentials`.
    assert source.count("apply_dify_metadata_if_enabled(credentials)") == 2
    # The `_invoke` call is placed AFTER messages are built and BEFORE the
    # `inference(...)` call so the helper has a chance to set
    # `credentials[_dify_metadata]` before `inference` reads it.
    invoke_idx = source.index("def _invoke(")
    # Read a wide enough window to span both the helper call and the
    # inference call.
    invoke_block = source[invoke_idx : invoke_idx + 6000]
    idx_helper = invoke_block.index("apply_dify_metadata_if_enabled(credentials)")
    # The `extra_metadata=` kwarg appears only at the inference call site
    # (not in the function definition), so this directly targets the call.
    idx_call = invoke_block.index("response = inference(")
    idx_extra_metadata = invoke_block.index("extra_metadata=")
    assert idx_helper < idx_call
    assert idx_call < idx_extra_metadata


def test_helper_module_is_reachable_from_llm() -> None:
    helper_path = ROOT_DIR / "models" / "llm" / "_metadata.py"
    assert helper_path.is_file(), f"missing helper: {helper_path}"
    import models.llm._metadata as helper_module

    assert hasattr(helper_module, "apply_dify_metadata_if_enabled")
    assert callable(helper_module.apply_dify_metadata_if_enabled)
    assert hasattr(helper_module, "build_dify_metadata")
    assert callable(helper_module.build_dify_metadata)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-vv"]))
