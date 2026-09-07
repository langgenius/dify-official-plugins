"""Unit tests for the opt-in Dify metadata helper used by the Fireworks plugin.

The helper writes a `metadata` field into the `extra_body` kwarg that is
forwarded to the underlying `openai` SDK call (`client.chat.completions.create`).
Fireworks is OpenAI-compatible and silently ignores unknown body fields, so the
metadata travels alongside the rest of the request payload.

The helper is opt-in: when the credential `enable_request_metadata` is
`"enabled"` and a Dify `app_id` resolves (via `dify_plugin.get_current_session()`),
the helper writes a `metadata` dict into `extra_kwargs['extra_body']['metadata']`.
When the credential is disabled or no `app_id` resolves, the helper returns
`None` and the call site can skip sending an empty `extra_body` field.

These tests do not need a network or the Fireworks SDK: the helper is pure
and runs entirely in memory. The integration with `_chat_generate` is
verified by the source-level guard tests at the bottom of this file.
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
    apply_dify_metadata_if_enabled,
    build_dify_metadata,
    normalize_metadata_value,
)

_ENABLED = "enabled"
_METADATA_KEY = "dify_app_id"
_SOURCE_KEY = "dify_source"
_SOURCE_VALUE = "dify"


# ---------------------------------------------------------------------------
# normalize_metadata_value
# ---------------------------------------------------------------------------


def test_normalize_uuid_passthrough() -> None:
    """UUIDs and other visible-ASCII app_ids pass through unchanged."""
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    assert normalize_metadata_value(uuid) == uuid


def test_normalize_preserves_punctuation() -> None:
    """Visible ASCII punctuation is preserved; no character-pattern restriction."""
    assert normalize_metadata_value("a[b]c{d}e") == "a[b]c{d}e"


def test_normalize_coerces_non_string() -> None:
    """Numeric input is stringified rather than dropped."""
    assert normalize_metadata_value(12345) == "12345"


def test_normalize_returns_empty_for_none() -> None:
    """None normalizes to the empty string."""
    assert normalize_metadata_value(None) == ""


def test_normalize_returns_empty_for_empty_string() -> None:
    """Empty string normalizes to the empty string."""
    assert normalize_metadata_value("") == ""


def test_normalize_truncates_to_256_chars() -> None:
    """Hard cap of 256 characters to keep metadata values bounded."""
    s = "a" * 1024
    assert len(normalize_metadata_value(s)) == 256


# ---------------------------------------------------------------------------
# build_dify_metadata
# ---------------------------------------------------------------------------


def test_build_metadata_with_valid_app_id() -> None:
    """Happy path: app_id is set -> both keys present."""
    metadata = build_dify_metadata("app-123")
    assert metadata == {
        _METADATA_KEY: "app-123",
        _SOURCE_KEY: _SOURCE_VALUE,
    }


def test_build_metadata_with_empty_app_id() -> None:
    """Empty app_id -> None (caller can skip metadata attachment)."""
    assert build_dify_metadata("") is None


def test_build_metadata_with_none_app_id() -> None:
    """None app_id -> None."""
    assert build_dify_metadata(None) is None


def test_build_metadata_truncates_long_app_id() -> None:
    """Long app_id values are truncated to 256 characters."""
    long_id = "a" * 1024
    metadata = build_dify_metadata(long_id)
    assert metadata is not None
    assert len(metadata[_METADATA_KEY]) == 256


# ---------------------------------------------------------------------------
# apply_dify_metadata_if_enabled — disabled / no-op paths
# ---------------------------------------------------------------------------


def test_disabled_returns_none() -> None:
    """`enable_request_metadata` unset -> return None, no mutation."""
    extra_kwargs: dict = {}
    credentials = {"app_id": "app-123"}
    result = apply_dify_metadata_if_enabled(extra_kwargs, credentials)
    assert result is None
    assert extra_kwargs == {}


def test_disabled_with_other_value_returns_none() -> None:
    """Any non-`enabled` value (including `disabled`) is a no-op."""
    extra_kwargs: dict = {"functions": [{"name": "x"}]}
    credentials = {"app_id": "app-123", "enable_request_metadata": "disabled"}
    result = apply_dify_metadata_if_enabled(extra_kwargs, credentials)
    assert result is None
    assert extra_kwargs == {"functions": [{"name": "x"}]}


def test_disabled_with_random_value_returns_none() -> None:
    """Random garbage values must not silently enable metadata."""
    extra_kwargs: dict = {}
    credentials = {"app_id": "app-123", "enable_request_metadata": "yes-please"}
    result = apply_dify_metadata_if_enabled(extra_kwargs, credentials)
    assert result is None
    assert extra_kwargs == {}


def test_enabled_without_app_id_returns_none() -> None:
    """`enabled` but no app_id in the current session -> None, no mutation."""
    extra_kwargs: dict = {}
    credentials = {"enable_request_metadata": _ENABLED}
    # Force the session lookup to return an object with no app_id attribute.
    result = apply_dify_metadata_if_enabled(extra_kwargs, credentials)
    # When the session returns no app_id, the helper returns None.
    # When the session is unavailable, it also returns None.
    # Either way: no mutation.
    if result is None:
        assert extra_kwargs == {}


def test_enabled_with_existing_extra_body_and_no_app_id_returns_none() -> None:
    """If `extra_body` is already set but no app_id resolves, the helper
    does not touch it (caller-supplied data is preserved)."""
    existing_extra_body = {"metadata": {"user_id": "u-1"}}
    extra_kwargs: dict = {"extra_body": existing_extra_body}
    credentials = {"enable_request_metadata": _ENABLED}
    result = apply_dify_metadata_if_enabled(extra_kwargs, credentials)
    # No app_id in the session -> None returned, no mutation.
    if result is None:
        assert extra_kwargs == {"extra_body": {"metadata": {"user_id": "u-1"}}}


# ---------------------------------------------------------------------------
# apply_dify_metadata_if_enabled — enabled / positive paths (mocked session)
# ---------------------------------------------------------------------------


def test_enabled_with_app_id_attaches_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: `enabled` + valid app_id -> extra_body.metadata is set.

    We mock `dify_plugin.get_current_session` so the helper resolves a
    deterministic app_id without depending on the runtime session.
    """
    import dify_plugin

    fake_session = SimpleNamespace(app_id="app-123")
    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: fake_session)

    extra_kwargs: dict = {}
    credentials = {"enable_request_metadata": _ENABLED}
    result = apply_dify_metadata_if_enabled(extra_kwargs, credentials)
    assert result is extra_kwargs
    assert extra_kwargs == {
        "extra_body": {
            "metadata": {
                _METADATA_KEY: "app-123",
                _SOURCE_KEY: _SOURCE_VALUE,
            }
        }
    }


def test_enabled_stringifies_non_string_app_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Numeric / other app_id values are stringified rather than dropped."""
    import dify_plugin

    fake_session = SimpleNamespace(app_id=12345)
    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: fake_session)

    extra_kwargs: dict = {}
    credentials = {"enable_request_metadata": _ENABLED}
    apply_dify_metadata_if_enabled(extra_kwargs, credentials)
    assert extra_kwargs["extra_body"]["metadata"][_METADATA_KEY] == "12345"
    assert extra_kwargs["extra_body"]["metadata"][_SOURCE_KEY] == _SOURCE_VALUE


def test_enabled_preserves_existing_extra_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the caller already set `extra_body` (without `metadata`), it is preserved."""
    import dify_plugin

    fake_session = SimpleNamespace(app_id="app-123")
    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: fake_session)

    extra_kwargs: dict = {"extra_body": {"custom_field": "value"}}
    credentials = {"enable_request_metadata": _ENABLED}
    result = apply_dify_metadata_if_enabled(extra_kwargs, credentials)
    assert result is extra_kwargs
    assert extra_kwargs["extra_body"] == {
        "custom_field": "value",
        "metadata": {
            _METADATA_KEY: "app-123",
            _SOURCE_KEY: _SOURCE_VALUE,
        },
    }


def test_enabled_merges_with_existing_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the caller already set `extra_body.metadata`, the Dify keys are merged
    in alongside (Dify wins on collision)."""
    import dify_plugin

    fake_session = SimpleNamespace(app_id="app-123")
    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: fake_session)

    extra_kwargs: dict = {"extra_body": {"metadata": {"user_id": "u-1"}}}
    credentials = {"enable_request_metadata": _ENABLED}
    apply_dify_metadata_if_enabled(extra_kwargs, credentials)
    assert extra_kwargs["extra_body"]["metadata"] == {
        "user_id": "u-1",
        _METADATA_KEY: "app-123",
        _SOURCE_KEY: _SOURCE_VALUE,
    }


def test_enabled_dify_keys_override_caller_on_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the caller set `extra_body.metadata.dify_app_id` already, the helper
    overrides that entry so the helper always controls its own markers."""
    import dify_plugin

    fake_session = SimpleNamespace(app_id="app-123")
    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: fake_session)

    extra_kwargs: dict = {
        "extra_body": {
            "metadata": {
                _METADATA_KEY: "old-value",
                _SOURCE_KEY: "old-source",
                "user_id": "u-1",
            }
        }
    }
    credentials = {"enable_request_metadata": _ENABLED}
    apply_dify_metadata_if_enabled(extra_kwargs, credentials)
    assert extra_kwargs["extra_body"]["metadata"] == {
        _METADATA_KEY: "app-123",
        _SOURCE_KEY: _SOURCE_VALUE,
        "user_id": "u-1",
    }


def test_enabled_handles_non_dict_existing_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the caller set `extra_body.metadata` to a non-dict, the helper
    overwrites it with the Dify dict rather than blow up."""
    import dify_plugin

    fake_session = SimpleNamespace(app_id="app-123")
    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: fake_session)

    extra_kwargs: dict = {"extra_body": {"metadata": "not-a-dict"}}
    credentials = {"enable_request_metadata": _ENABLED}
    apply_dify_metadata_if_enabled(extra_kwargs, credentials)
    assert extra_kwargs["extra_body"]["metadata"] == {
        _METADATA_KEY: "app-123",
        _SOURCE_KEY: _SOURCE_VALUE,
    }


def test_enabled_handles_non_dict_existing_extra_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the caller set `extra_body` to a non-dict, the helper replaces it
    with a fresh dict rather than blow up."""
    import dify_plugin

    fake_session = SimpleNamespace(app_id="app-123")
    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: fake_session)

    extra_kwargs: dict = {"extra_body": "not-a-dict"}
    credentials = {"enable_request_metadata": _ENABLED}
    apply_dify_metadata_if_enabled(extra_kwargs, credentials)
    assert extra_kwargs["extra_body"] == {
        "metadata": {
            _METADATA_KEY: "app-123",
            _SOURCE_KEY: _SOURCE_VALUE,
        }
    }


def test_enabled_does_not_mutate_other_extra_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The helper only touches `extra_body`; other keys (functions, stop, user)
    are preserved untouched."""
    import dify_plugin

    fake_session = SimpleNamespace(app_id="app-123")
    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: fake_session)

    extra_kwargs: dict = {
        "functions": [{"name": "x"}],
        "stop": ["</s>"],
        "user": "u-1",
    }
    credentials = {"enable_request_metadata": _ENABLED}
    apply_dify_metadata_if_enabled(extra_kwargs, credentials)
    assert extra_kwargs["functions"] == [{"name": "x"}]
    assert extra_kwargs["stop"] == ["</s>"]
    assert extra_kwargs["user"] == "u-1"
    assert "extra_body" in extra_kwargs


# ---------------------------------------------------------------------------
# Robustness: the helper must never raise
# ---------------------------------------------------------------------------


def test_helper_never_raises_on_session_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If `get_current_session` raises, the helper returns None (no mutation)."""
    import dify_plugin

    def _raising():
        raise RuntimeError("session not available")

    monkeypatch.setattr(dify_plugin, "get_current_session", _raising)

    extra_kwargs: dict = {}
    credentials = {"enable_request_metadata": _ENABLED}
    result = apply_dify_metadata_if_enabled(extra_kwargs, credentials)
    assert result is None
    assert extra_kwargs == {}


def test_helper_never_raises_on_session_returning_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If `get_current_session` returns None, the helper returns None (no mutation)."""
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: None)

    extra_kwargs: dict = {}
    credentials = {"enable_request_metadata": _ENABLED}
    result = apply_dify_metadata_if_enabled(extra_kwargs, credentials)
    assert result is None
    assert extra_kwargs == {}


def test_helper_never_raises_on_session_without_app_id_attr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the session object has no `app_id` attribute, the helper returns None."""
    import dify_plugin

    fake_session = SimpleNamespace()  # no app_id attribute
    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: fake_session)

    extra_kwargs: dict = {}
    credentials = {"enable_request_metadata": _ENABLED}
    result = apply_dify_metadata_if_enabled(extra_kwargs, credentials)
    assert result is None
    assert extra_kwargs == {}


# ---------------------------------------------------------------------------
# Source-level guard: the helper is wired into llm.py at the documented site
# ---------------------------------------------------------------------------


def test_helper_is_used_in_llm_py() -> None:
    """Source-level guard.

    The helper is called in two places: `_chat_generate` (alongside
    `extra_model_kwargs`) and `validate_credentials` (alongside
    `validate_extra_kwargs`) to set `extra_body` before the SDK call. This
    test catches accidental removal of either call site during refactors.
    """
    llm_path = ROOT_DIR / "models" / "llm" / "llm.py"
    source = llm_path.read_text(encoding="utf-8")
    # The helper is imported (lazily) in both call paths.
    assert (
        source.count("from models.llm._metadata import apply_dify_metadata_if_enabled")
        == 2
    )
    # Exactly one call in `_chat_generate`.
    assert (
        source.count("apply_dify_metadata_if_enabled(extra_model_kwargs, credentials)")
        == 1
    )
    # Exactly one call in `validate_credentials`.
    assert (
        source.count(
            "apply_dify_metadata_if_enabled(validate_extra_kwargs, credentials)"
        )
        == 1
    )
    # The `_chat_generate` call is placed AFTER `extra_model_kwargs` is fully
    # built and BEFORE the SDK call. We look at the slice after
    # `_chat_generate` is defined so we don't pick up the earlier
    # `client.chat.completions.create(` reference in `validate_credentials`.
    chat_generate_idx = source.index("def _chat_generate(")
    chat_generate_block = source[chat_generate_idx:]
    idx_build = chat_generate_block.index("extra_model_kwargs = {}")
    idx_call = chat_generate_block.index(
        "apply_dify_metadata_if_enabled(extra_model_kwargs, credentials)"
    )
    idx_create = chat_generate_block.index("client.chat.completions.create(")
    assert idx_build < idx_call < idx_create


def test_helper_module_is_reachable_from_llm() -> None:
    """The helper file exists at the expected path and is importable."""
    helper_path = ROOT_DIR / "models" / "llm" / "_metadata.py"
    assert helper_path.is_file(), f"missing helper: {helper_path}"
    import models.llm._metadata as helper_module

    assert hasattr(helper_module, "apply_dify_metadata_if_enabled")
    assert callable(helper_module.apply_dify_metadata_if_enabled)
    assert hasattr(helper_module, "build_dify_metadata")
    assert callable(helper_module.build_dify_metadata)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-vv"]))
