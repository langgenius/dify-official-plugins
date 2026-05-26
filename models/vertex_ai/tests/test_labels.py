from models.llm._labels import (
    apply_dify_labels_if_enabled,
    build_dify_labels,
    normalize_label_value,
)


def test_normalize_uuid_passthrough():
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    assert normalize_label_value(uuid) == uuid


def test_normalize_replaces_invalid_chars():
    assert normalize_label_value("a@b.c") == "a_b_c"


def test_normalize_truncates_at_63_chars():
    long_input = "a" * 100
    result = normalize_label_value(long_input)
    assert len(result) == 63
    assert result == "a" * 63


def test_normalize_lowercases_uppercase():
    assert normalize_label_value("FOO-BAR") == "foo-bar"


def test_normalize_empty_string():
    assert normalize_label_value("") == ""


def test_normalize_coerces_non_string_input():
    # Non-string inputs should be stringified before validation, so a
    # numeric 0 (falsy) does not get dropped by the empty-check.
    assert normalize_label_value(0) == "0"
    assert normalize_label_value(123) == "123"


def test_build_dify_labels_returns_none_for_none():
    assert build_dify_labels(None) is None


def test_build_dify_labels_returns_none_for_empty():
    assert build_dify_labels("") is None


def test_build_dify_labels_includes_source_marker():
    labels = build_dify_labels("550e8400-e29b-41d4-a716-446655440000")
    assert labels is not None
    assert labels["dify_source"] == "dify"


def test_build_dify_labels_normalizes_app_id():
    labels = build_dify_labels("My App@Example.com/" + "x" * 100)
    assert labels is not None
    app_id = labels["dify_app_id"]
    assert len(app_id) <= 63
    assert all(c.islower() or c.isdigit() or c in "_-" for c in app_id)


def test_build_dify_labels_keeps_non_string_falsy():
    # build_dify_labels only rejects None and "" — other falsy values
    # such as numeric 0 are coerced by normalize_label_value.
    labels = build_dify_labels(0)
    assert labels == {"dify_app_id": "0", "dify_source": "dify"}


def test_apply_no_op_when_credential_missing():
    config_kwargs: dict = {}
    apply_dify_labels_if_enabled(config_kwargs, {})
    assert config_kwargs == {}


def test_apply_no_op_when_credential_disabled():
    config_kwargs: dict = {}
    apply_dify_labels_if_enabled(config_kwargs, {"enable_request_metadata": "disabled"})
    assert config_kwargs == {}


def test_apply_silent_on_session_lookup_failure():
    # Without a Dify session context, get_current_session raises; the
    # helper must swallow that and leave config_kwargs unchanged.
    config_kwargs: dict = {}
    apply_dify_labels_if_enabled(config_kwargs, {"enable_request_metadata": "enabled"})
    assert "labels" not in config_kwargs


class _FakeSession:
    app_id = "550e8400-e29b-41d4-a716-446655440000"


def test_apply_merges_with_existing_labels(monkeypatch):
    # When config_kwargs already carries labels (e.g. caller-supplied
    # values), Dify keys must merge into them rather than replace them.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    config_kwargs: dict = {"labels": {"team": "billing"}}
    apply_dify_labels_if_enabled(config_kwargs, {"enable_request_metadata": "enabled"})
    assert config_kwargs["labels"]["team"] == "billing"
    assert config_kwargs["labels"]["dify_app_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert config_kwargs["labels"]["dify_source"] == "dify"


def test_apply_replaces_non_dict_labels(monkeypatch):
    # If existing labels is somehow not a dict, Dify keys take over rather
    # than blow up — telemetry is best-effort.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    config_kwargs: dict = {"labels": "unexpected-string"}
    apply_dify_labels_if_enabled(config_kwargs, {"enable_request_metadata": "enabled"})
    assert isinstance(config_kwargs["labels"], dict)
    assert config_kwargs["labels"]["dify_app_id"] == "550e8400-e29b-41d4-a716-446655440000"
