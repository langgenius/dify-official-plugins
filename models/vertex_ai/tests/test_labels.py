from models.llm._labels import build_dify_labels, normalize_label_value


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
