from models.llm._metadata import build_dify_request_metadata, normalize_metadata_value


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
