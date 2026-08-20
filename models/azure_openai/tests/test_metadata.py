from models.llm._metadata import (
    apply_dify_metadata_if_enabled,
    build_dify_metadata,
    normalize_metadata_value,
)


def test_normalize_uuid_passthrough():
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    assert normalize_metadata_value(uuid) == uuid


def test_normalize_preserves_punctuation_and_unicode():
    # OpenAI does not document a character pattern restriction; values are
    # only length-bounded. Brackets, slashes, and non-ASCII pass through.
    assert normalize_metadata_value("a[b]c") == "a[b]c"
    assert normalize_metadata_value("日本語") == "日本語"


def test_normalize_preserves_mixed_case():
    assert normalize_metadata_value("FOO-Bar") == "FOO-Bar"


def test_normalize_truncates_at_512_chars():
    long_input = "a" * 600
    result = normalize_metadata_value(long_input)
    assert len(result) == 512
    assert result == "a" * 512


def test_normalize_empty_string():
    assert normalize_metadata_value("") == ""


def test_normalize_coerces_non_string_input():
    # Non-string inputs should be stringified before validation, so a
    # numeric 0 (falsy) does not get dropped by the empty-check.
    assert normalize_metadata_value(0) == "0"
    assert normalize_metadata_value(123) == "123"


def test_build_dify_metadata_returns_none_for_none():
    assert build_dify_metadata(None) is None


def test_build_dify_metadata_returns_none_for_empty():
    assert build_dify_metadata("") is None


def test_build_dify_metadata_keeps_non_string_falsy():
    # build_dify_metadata only rejects None and "" — other falsy values
    # such as numeric 0 are coerced by normalize_metadata_value.
    metadata = build_dify_metadata(0)
    assert metadata == {"dify_app_id": "0", "dify_source": "dify"}


def test_build_dify_metadata_includes_source_marker():
    metadata = build_dify_metadata("550e8400-e29b-41d4-a716-446655440000")
    assert metadata is not None
    assert metadata["dify_source"] == "dify"


def test_build_dify_metadata_normalizes_app_id_length():
    metadata = build_dify_metadata("x" * 1000)
    assert metadata is not None
    assert len(metadata["dify_app_id"]) == 512


def test_build_dify_metadata_uuid_passthrough():
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    metadata = build_dify_metadata(uuid)
    assert metadata == {"dify_app_id": uuid, "dify_source": "dify"}


def test_apply_no_op_when_credential_missing():
    target: dict = {}
    apply_dify_metadata_if_enabled(target, {})
    assert target == {}


def test_apply_no_op_when_credential_disabled():
    target: dict = {}
    apply_dify_metadata_if_enabled(target, {"enable_request_metadata": "disabled"})
    assert target == {}


# Metadata requires an api-version that supports Stored Completions. The
# plugin's fallback default predates it, so the enabled-path tests have to be
# explicit about the version, exactly as a working deployment must be.
ENABLED = {
    "enable_request_metadata": "enabled",
    "openai_api_version": "2025-04-01-preview",
}


def test_apply_noop_without_session_context():
    # Outside a Dify session, get_current_session() returns None rather than
    # raising, so no app_id resolves and target is left untouched.
    target: dict = {}
    apply_dify_metadata_if_enabled(target, ENABLED)
    assert "metadata" not in target
    assert "store" not in target


def test_apply_silent_when_session_lookup_raises(monkeypatch):
    # Telemetry must never break generation, so a raising session lookup is
    # swallowed. Exercises the except branch directly, which the None-returning
    # path above cannot reach.
    import dify_plugin

    def _boom():
        raise RuntimeError("session backend unavailable")

    monkeypatch.setattr(dify_plugin, "get_current_session", _boom)
    target: dict = {}
    apply_dify_metadata_if_enabled(target, ENABLED)
    assert "metadata" not in target
    assert "store" not in target


class _FakeSession:
    app_id = "550e8400-e29b-41d4-a716-446655440000"


def test_apply_skipped_when_api_version_predates_stored_completions(monkeypatch):
    # An api-version older than Stored Completions rejects metadata outright,
    # which would fail every generation. Telemetry is dropped instead.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    target: dict = {}
    apply_dify_metadata_if_enabled(
        target,
        {
            "enable_request_metadata": "enabled",
            "openai_api_version": "2024-02-15-preview",
        },
    )
    assert "metadata" not in target
    assert "store" not in target


def test_apply_skipped_when_api_version_left_empty(monkeypatch):
    # openai_api_version is optional, and the fallback default also predates
    # Stored Completions, so an empty value must be treated as unsupported.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    target: dict = {}
    apply_dify_metadata_if_enabled(target, {"enable_request_metadata": "enabled"})
    assert "metadata" not in target


def test_apply_allowed_on_versionless_v1_endpoint(monkeypatch):
    # /openai/v1 endpoints are versionless — common.py omits api_version for
    # them — and support metadata regardless of the dropdown value.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    target: dict = {}
    apply_dify_metadata_if_enabled(
        target,
        {
            "enable_request_metadata": "enabled",
            "openai_api_base": "https://example.openai.azure.com/openai/v1",
        },
    )
    assert target["metadata"]["dify_app_id"] == _FakeSession.app_id
    assert target["store"] is True


def test_apply_merges_with_existing_metadata(monkeypatch):
    # When the target already carries a metadata dict (e.g. caller-supplied
    # values), Dify keys must merge into it rather than replace it wholesale.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    target: dict = {"metadata": {"user_supplied": "value"}}
    apply_dify_metadata_if_enabled(target, ENABLED)
    assert target["metadata"]["user_supplied"] == "value"
    assert target["metadata"]["dify_app_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert target["metadata"]["dify_source"] == "dify"


def test_apply_replaces_non_dict_metadata(monkeypatch):
    # If existing metadata is somehow not a dict, Dify keys take over rather
    # than blow up — telemetry is best-effort.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    target: dict = {"metadata": "unexpected-string"}
    apply_dify_metadata_if_enabled(target, ENABLED)
    assert isinstance(target["metadata"], dict)
    assert target["metadata"]["dify_app_id"] == "550e8400-e29b-41d4-a716-446655440000"


def test_apply_does_not_mutate_existing_metadata(monkeypatch):
    # The merge must not mutate the caller's dict in place: a shared reference
    # must never be modified as a side effect of telemetry opt-in.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    original = {"existing_key": "existing_value"}
    target: dict = {"metadata": original}
    apply_dify_metadata_if_enabled(target, ENABLED)
    # The original dict is left untouched.
    assert original == {"existing_key": "existing_value"}
    # target carries a new, merged dict.
    assert target["metadata"] is not original
    assert target["metadata"]["existing_key"] == "existing_value"
    assert target["metadata"]["dify_app_id"] == "550e8400-e29b-41d4-a716-446655440000"


def test_apply_sets_store_true(monkeypatch):
    # The API only accepts metadata when store=true, so applying the metadata
    # must also enable store.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    target: dict = {}
    apply_dify_metadata_if_enabled(target, ENABLED)
    assert target["store"] is True


def test_apply_skips_metadata_when_store_is_explicitly_false(monkeypatch):
    # An explicit store value set by the caller must be respected. Because the
    # API rejects metadata unless store is true, respecting store=False also
    # means skipping the metadata entirely rather than emitting a request that
    # is guaranteed to fail.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    target: dict = {"store": False}
    apply_dify_metadata_if_enabled(target, ENABLED)
    assert target["store"] is False
    assert "metadata" not in target


def test_apply_disabled_does_not_touch_store():
    # When the feature is disabled or unset, store must not be touched.
    target: dict = {}
    apply_dify_metadata_if_enabled(target, {"enable_request_metadata": "disabled"})
    assert "store" not in target

    target_unset: dict = {}
    apply_dify_metadata_if_enabled(target_unset, {})
    assert "store" not in target_unset


def test_normalize_none_returns_empty():
    assert normalize_metadata_value(None) == ""
