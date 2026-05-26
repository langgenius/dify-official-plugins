from models.llm._metadata import (
    apply_dify_request_metadata_if_enabled,
    build_dify_request_metadata,
    normalize_metadata_value,
)


def test_normalize_uuid_passthrough():
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    assert normalize_metadata_value(uuid) == uuid


def test_normalize_replaces_invalid_chars():
    # Square brackets are not in the allowed set; should be replaced with `_`.
    assert normalize_metadata_value("a[b]c") == "a_b_c"


def test_normalize_preserves_allowed_special_chars():
    # Bedrock allows :_@$#=/+,-. and whitespace.
    value = "a:b_c@d$e#f=g/h+i,j-k.l m"
    assert normalize_metadata_value(value) == value


def test_normalize_preserves_mixed_case():
    # Unlike Vertex AI, Bedrock allows uppercase letters.
    assert normalize_metadata_value("FOO-Bar") == "FOO-Bar"


def test_normalize_truncates_at_256_chars():
    long_input = "a" * 300
    result = normalize_metadata_value(long_input)
    assert len(result) == 256
    assert result == "a" * 256


def test_normalize_empty_string():
    assert normalize_metadata_value("") == ""


def test_normalize_replaces_non_ascii():
    # Non-ASCII characters fall outside the allowed pattern.
    assert normalize_metadata_value("日本語") == "___"


def test_normalize_coerces_non_string_input():
    # Non-string inputs should be stringified before validation, so a
    # numeric 0 (falsy) does not get dropped by the empty-check.
    assert normalize_metadata_value(0) == "0"
    assert normalize_metadata_value(123) == "123"


def test_build_dify_request_metadata_returns_none_for_none():
    assert build_dify_request_metadata(None) is None


def test_build_dify_request_metadata_returns_none_for_empty():
    assert build_dify_request_metadata("") is None


def test_build_dify_request_metadata_includes_source_marker():
    metadata = build_dify_request_metadata("550e8400-e29b-41d4-a716-446655440000")
    assert metadata is not None
    assert metadata["dify_source"] == "dify"


def test_build_dify_request_metadata_normalizes_app_id():
    metadata = build_dify_request_metadata("My App[Example]/" + "x" * 300)
    assert metadata is not None
    app_id = metadata["dify_app_id"]
    assert len(app_id) <= 256
    # Should not contain disallowed chars; brackets were replaced.
    assert "[" not in app_id
    assert "]" not in app_id


def test_build_dify_request_metadata_uuid_passthrough():
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    metadata = build_dify_request_metadata(uuid)
    assert metadata == {"dify_app_id": uuid, "dify_source": "dify"}


def test_build_dify_request_metadata_keeps_non_string_falsy():
    # build_dify_request_metadata only rejects None and "" — other falsy
    # values such as numeric 0 are coerced by normalize_metadata_value.
    metadata = build_dify_request_metadata(0)
    assert metadata == {"dify_app_id": "0", "dify_source": "dify"}


def test_apply_no_op_when_credential_missing():
    parameters: dict = {}
    apply_dify_request_metadata_if_enabled(parameters, {})
    assert parameters == {}


def test_apply_no_op_when_credential_disabled():
    parameters: dict = {}
    apply_dify_request_metadata_if_enabled(parameters, {"enable_request_metadata": "disabled"})
    assert parameters == {}


def test_apply_silent_on_session_lookup_failure():
    # Without a Dify session context, get_current_session raises; the
    # helper must swallow that and leave parameters unchanged.
    parameters: dict = {}
    apply_dify_request_metadata_if_enabled(parameters, {"enable_request_metadata": "enabled"})
    assert "requestMetadata" not in parameters


class _FakeSession:
    app_id = "550e8400-e29b-41d4-a716-446655440000"


def test_apply_merges_with_existing_request_metadata(monkeypatch):
    # When parameters already carries requestMetadata (e.g. caller-supplied
    # values), Dify keys must merge into it rather than replace it wholesale.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    parameters: dict = {"requestMetadata": {"caller_tag": "manual"}}
    apply_dify_request_metadata_if_enabled(parameters, {"enable_request_metadata": "enabled"})
    assert parameters["requestMetadata"]["caller_tag"] == "manual"
    assert parameters["requestMetadata"]["dify_app_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert parameters["requestMetadata"]["dify_source"] == "dify"


def test_apply_replaces_non_dict_request_metadata(monkeypatch):
    # If existing requestMetadata is somehow not a dict, Dify keys take
    # over rather than blow up — telemetry is best-effort.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    parameters: dict = {"requestMetadata": "unexpected-string"}
    apply_dify_request_metadata_if_enabled(parameters, {"enable_request_metadata": "enabled"})
    assert isinstance(parameters["requestMetadata"], dict)
    assert parameters["requestMetadata"]["dify_app_id"] == "550e8400-e29b-41d4-a716-446655440000"
