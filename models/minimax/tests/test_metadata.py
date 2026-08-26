from models.llm._metadata import (
    apply_dify_metadata_if_enabled,
    build_dify_metadata,
    normalize_metadata_value,
)


# --- normalize_metadata_value ---


def test_normalize_uuid_passthrough():
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    assert normalize_metadata_value(uuid) == uuid


def test_normalize_preserves_punctuation_and_unicode():
    # The Anthropic-compatible metadata field accepts arbitrary
    # string values, so punctuation and non-ASCII pass through
    # unchanged.
    assert normalize_metadata_value("a[b]c") == "a[b]c"
    assert normalize_metadata_value("日本語") == "日本語"


def test_normalize_preserves_mixed_case():
    assert normalize_metadata_value("FOO-Bar") == "FOO-Bar"


def test_normalize_truncates_at_256_chars():
    long_input = "a" * 600
    result = normalize_metadata_value(long_input)
    assert len(result) == 256
    assert result == "a" * 256


def test_normalize_empty_string():
    assert normalize_metadata_value("") == ""


def test_normalize_coerces_non_string_input():
    assert normalize_metadata_value(0) == "0"
    assert normalize_metadata_value(123) == "123"


# --- build_dify_metadata ---


def test_build_dify_metadata_returns_none_for_none():
    assert build_dify_metadata(None) is None


def test_build_dify_metadata_returns_none_for_empty():
    assert build_dify_metadata("") is None


def test_build_dify_metadata_keeps_non_string_falsy():
    metadata = build_dify_metadata(0)
    assert metadata == {"dify_app_id": "0", "dify_source": "dify"}


def test_build_dify_metadata_includes_source_marker():
    metadata = build_dify_metadata("550e8400-e29b-41d4-a716-446655440000")
    assert metadata is not None
    assert metadata["dify_source"] == "dify"


def test_build_dify_metadata_normalizes_app_id_length():
    metadata = build_dify_metadata("x" * 1000)
    assert metadata is not None
    assert len(metadata["dify_app_id"]) == 256


def test_build_dify_metadata_uuid_passthrough():
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    metadata = build_dify_metadata(uuid)
    assert metadata == {"dify_app_id": uuid, "dify_source": "dify"}


# --- apply_dify_metadata_if_enabled: credential gating ---


def test_apply_returns_none_when_credential_missing():
    request_kwargs: dict = {"model": "MiniMax-M1"}
    result = apply_dify_metadata_if_enabled(request_kwargs, {})
    assert result is None
    # Original input is left intact.
    assert request_kwargs == {"model": "MiniMax-M1"}


def test_apply_returns_none_when_credential_disabled():
    request_kwargs: dict = {"model": "MiniMax-M1"}
    result = apply_dify_metadata_if_enabled(
        request_kwargs, {"enable_request_metadata": "disabled"}
    )
    assert result is None
    assert request_kwargs == {"model": "MiniMax-M1"}


def test_apply_disabled_preserves_existing_user_id(monkeypatch):
    # Regression guard: when the credential is disabled, the helper
    # must NOT touch the existing metadata dict (even if a caller-
    # supplied `user_id` is already there). This matters because
    # MiniMax's LLM invocation sets `metadata = {"user_id": user}`
    # unconditionally when the request's user is set; the helper must
    # leave that key alone when disabled.
    request_kwargs: dict = {
        "model": "MiniMax-M1",
        "metadata": {"user_id": "end-user-1234"},
    }
    result = apply_dify_metadata_if_enabled(
        request_kwargs, {"enable_request_metadata": "disabled"}
    )
    assert result is None
    assert request_kwargs == {
        "model": "MiniMax-M1",
        "metadata": {"user_id": "end-user-1234"},
    }


def test_apply_returns_none_without_session_context():
    request_kwargs: dict = {"model": "MiniMax-M1"}
    result = apply_dify_metadata_if_enabled(
        request_kwargs, {"enable_request_metadata": "enabled"}
    )
    # No app_id resolves, so no metadata is attached.
    assert result is None
    assert request_kwargs == {"model": "MiniMax-M1"}


def test_apply_silent_when_session_lookup_raises(monkeypatch):
    import dify_plugin

    def _boom():
        raise RuntimeError("session backend unavailable")

    monkeypatch.setattr(dify_plugin, "get_current_session", _boom)
    request_kwargs: dict = {"model": "MiniMax-M1"}
    result = apply_dify_metadata_if_enabled(
        request_kwargs, {"enable_request_metadata": "enabled"}
    )
    # No app_id resolves, so no metadata is attached.
    assert result is None
    assert request_kwargs == {"model": "MiniMax-M1"}


class _FakeSession:
    app_id = "550e8400-e29b-41d4-a716-446655440000"


# --- apply_dify_metadata_if_enabled: metadata composition ---


def test_apply_merges_with_existing_metadata(monkeypatch):
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    request_kwargs: dict = {"model": "MiniMax-M1", "metadata": {"user_id": "end-user-1234"}}
    result = apply_dify_metadata_if_enabled(
        request_kwargs, {"enable_request_metadata": "enabled"}
    )
    # Returned value is the same (mutated) request_kwargs.
    assert result is request_kwargs
    assert request_kwargs["metadata"]["user_id"] == "end-user-1234"
    assert request_kwargs["metadata"]["dify_app_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert request_kwargs["metadata"]["dify_source"] == "dify"


def test_apply_replaces_non_dict_metadata(monkeypatch):
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    request_kwargs: dict = {"model": "MiniMax-M1", "metadata": "unexpected-string"}
    apply_dify_metadata_if_enabled(
        request_kwargs, {"enable_request_metadata": "enabled"}
    )
    assert isinstance(request_kwargs["metadata"], dict)
    assert request_kwargs["metadata"]["dify_app_id"] == "550e8400-e29b-41d4-a716-446655440000"


def test_apply_does_not_mutate_other_request_kwargs(monkeypatch):
    # Only the metadata key is touched. Other request keys (model,
    # messages, max_tokens, etc.) are preserved.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    request_kwargs: dict = {
        "model": "MiniMax-M1",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": "hi"}],
    }
    apply_dify_metadata_if_enabled(
        request_kwargs, {"enable_request_metadata": "enabled"}
    )
    assert request_kwargs["model"] == "MiniMax-M1"
    assert request_kwargs["max_tokens"] == 1024
    assert request_kwargs["messages"] == [{"role": "user", "content": "hi"}]
    assert request_kwargs["metadata"]["dify_app_id"] == "550e8400-e29b-41d4-a716-446655440000"


def test_apply_writes_metadata_when_request_kwargs_empty(monkeypatch):
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    request_kwargs: dict = {}
    result = apply_dify_metadata_if_enabled(
        request_kwargs, {"enable_request_metadata": "enabled"}
    )
    assert result is request_kwargs
    assert request_kwargs["metadata"] == {
        "dify_app_id": "550e8400-e29b-41d4-a716-446655440000",
        "dify_source": "dify",
    }


def test_apply_skips_when_no_app_id(monkeypatch):
    import dify_plugin

    class _EmptySession:
        app_id = None

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _EmptySession())
    request_kwargs: dict = {"model": "MiniMax-M1"}
    result = apply_dify_metadata_if_enabled(
        request_kwargs, {"enable_request_metadata": "enabled"}
    )
    assert result is None
    assert "metadata" not in request_kwargs


def test_apply_metadata_dify_keys_override_existing_collisions(monkeypatch):
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    request_kwargs: dict = {
        "model": "MiniMax-M1",
        "metadata": {"dify_app_id": "stale-value", "caller_field": "preserved"},
    }
    apply_dify_metadata_if_enabled(
        request_kwargs, {"enable_request_metadata": "enabled"}
    )
    assert request_kwargs["metadata"]["dify_app_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert request_kwargs["metadata"]["caller_field"] == "preserved"
    assert request_kwargs["metadata"]["dify_source"] == "dify"


# --- apply_dify_metadata_if_enabled: source-level guard ---


def test_llm_module_uses_dify_metadata_helper():
    import inspect

    from models.llm import llm as llm_module

    source = inspect.getsource(llm_module)
    assert "apply_dify_metadata_if_enabled(request_kwargs, credentials)" in source
    assert "from ._metadata import apply_dify_metadata_if_enabled" in source
