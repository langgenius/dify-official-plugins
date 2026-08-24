from models.llm._metadata import (
    apply_dify_headers_if_enabled,
    build_dify_headers,
    normalize_header_value,
)


# --- normalize_header_value ---


def test_normalize_uuid_passthrough():
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    assert normalize_header_value(uuid) == uuid


def test_normalize_preserves_punctuation():
    assert normalize_header_value("a[b]c") == "a[b]c"


def test_normalize_strips_non_ascii():
    assert normalize_header_value("日本語") == ""
    assert normalize_header_value("café") == "caf"


def test_normalize_strips_cr_lf_and_control_chars():
    assert normalize_header_value("a\nb") == "ab"
    assert normalize_header_value("a\rb") == "ab"
    assert normalize_header_value("a\r\nb") == "ab"
    assert normalize_header_value("a\x00b") == "ab"
    assert normalize_header_value("a\x1fb") == "ab"


def test_normalize_strips_whitespace_only_to_empty():
    assert normalize_header_value("   ") == ""
    assert normalize_header_value("\t\n") == ""


def test_normalize_preserves_mixed_case():
    assert normalize_header_value("FOO-Bar") == "FOO-Bar"


def test_normalize_truncates_at_256_chars():
    long_input = "a" * 600
    result = normalize_header_value(long_input)
    assert len(result) == 256
    assert result == "a" * 256


def test_normalize_empty_string():
    assert normalize_header_value("") == ""


def test_normalize_none_returns_empty():
    assert normalize_header_value(None) == ""


def test_normalize_coerces_non_string_input():
    assert normalize_header_value(0) == "0"
    assert normalize_header_value(123) == "123"


# --- build_dify_headers ---


def test_build_dify_headers_returns_none_for_none():
    assert build_dify_headers(None) is None


def test_build_dify_headers_returns_none_for_empty():
    assert build_dify_headers("") is None


def test_build_dify_headers_returns_none_for_whitespace_only():
    assert build_dify_headers("   ") is None


def test_build_dify_headers_returns_none_for_control_only():
    assert build_dify_headers("\n\r\x00") is None


def test_build_dify_headers_keeps_non_string_falsy():
    headers = build_dify_headers(0)
    assert headers == {"X-Dify-App-Id": "0", "X-Dify-Source": "dify"}


def test_build_dify_headers_includes_source_marker():
    headers = build_dify_headers("550e8400-e29b-41d4-a716-446655440000")
    assert headers is not None
    assert headers["X-Dify-Source"] == "dify"


def test_build_dify_headers_normalizes_app_id_length():
    headers = build_dify_headers("x" * 1000)
    assert headers is not None
    assert len(headers["X-Dify-App-Id"]) == 256


def test_build_dify_headers_uuid_passthrough():
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    headers = build_dify_headers(uuid)
    assert headers == {"X-Dify-App-Id": uuid, "X-Dify-Source": "dify"}


# --- apply_dify_headers_if_enabled: credential gating ---


def test_apply_returns_new_headers_when_credential_missing():
    headers: dict = {"x-dashscope-euid": "value"}
    result = apply_dify_headers_if_enabled(headers, {})
    assert result is not headers
    assert result == headers


def test_apply_returns_new_headers_when_credential_disabled():
    headers: dict = {"x-dashscope-euid": "value"}
    result = apply_dify_headers_if_enabled(headers, {"enable_request_metadata": "disabled"})
    assert result is not headers
    assert result == headers
    assert "X-Dify-App-Id" not in result


def test_apply_noop_without_session_context():
    headers: dict = {"x-dashscope-euid": "value"}
    result = apply_dify_headers_if_enabled(headers, {"enable_request_metadata": "enabled"})
    assert result is not headers
    assert "X-Dify-App-Id" not in result
    assert "X-Dify-Source" not in result


def test_apply_silent_when_session_lookup_raises(monkeypatch):
    import dify_plugin

    def _boom():
        raise RuntimeError("session backend unavailable")

    monkeypatch.setattr(dify_plugin, "get_current_session", _boom)
    headers: dict = {"x-dashscope-euid": "value"}
    result = apply_dify_headers_if_enabled(headers, {"enable_request_metadata": "enabled"})
    assert result is not headers
    assert "X-Dify-App-Id" not in result


class _FakeSession:
    app_id = "550e8400-e29b-41d4-a716-446655440000"


# --- apply_dify_headers_if_enabled: header composition ---


def test_apply_merges_with_existing_headers(monkeypatch):
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    headers: dict = {"x-dashscope-euid": "value"}
    result = apply_dify_headers_if_enabled(headers, {"enable_request_metadata": "enabled"})
    assert result["x-dashscope-euid"] == "value"
    assert result["X-Dify-App-Id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert result["X-Dify-Source"] == "dify"
    # Original headers dict is not mutated.
    assert "X-Dify-App-Id" not in headers


def test_apply_writes_headers_when_input_empty(monkeypatch):
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    result = apply_dify_headers_if_enabled({}, {"enable_request_metadata": "enabled"})
    assert result == {
        "X-Dify-App-Id": "550e8400-e29b-41d4-a716-446655440000",
        "X-Dify-Source": "dify",
    }


def test_apply_does_not_mutate_input_headers(monkeypatch):
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    original = {"x-dashscope-euid": "value"}
    result = apply_dify_headers_if_enabled(original, {"enable_request_metadata": "enabled"})
    assert original == {"x-dashscope-euid": "value"}
    assert result is not original
    assert result["x-dashscope-euid"] == "value"
    assert result["X-Dify-App-Id"] == "550e8400-e29b-41d4-a716-446655440000"


def test_apply_drops_caller_keys_with_lowercase_collision(monkeypatch):
    # HTTP header names are case-insensitive. Caller-supplied variants
    # of the Dify keys must be dropped so the request carries exactly
    # one header per logical name.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    headers: dict = {
        "x-dify-app-id": "stale-lowercase",
        "X-DIFY-APP-ID": "stale-uppercase",
        "X-Dify-Source": "stale-source",
        "x-dashscope-euid": "preserved",
    }
    result = apply_dify_headers_if_enabled(headers, {"enable_request_metadata": "enabled"})
    assert result["X-Dify-App-Id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert result["X-Dify-Source"] == "dify"
    assert "x-dify-app-id" not in result
    assert "X-DIFY-APP-ID" not in result
    assert result["x-dashscope-euid"] == "preserved"


def test_apply_skips_when_app_id_normalizes_to_empty(monkeypatch):
    import dify_plugin

    class _WhitespaceSession:
        app_id = "   "

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _WhitespaceSession())
    headers: dict = {"x-dashscope-euid": "value"}
    result = apply_dify_headers_if_enabled(headers, {"enable_request_metadata": "enabled"})
    # No Dify keys injected when app_id normalizes to empty.
    assert "X-Dify-App-Id" not in result
    assert result["x-dashscope-euid"] == "value"


# --- apply_dify_headers_if_enabled: source-level guard ---


def test_llm_module_uses_dify_headers_helper():
    import inspect

    from models.llm import llm as llm_module

    source = inspect.getsource(llm_module)
    # The class-level composition helper centralizes the merge between
    # the bury-point header and the Dify request-metadata helper.
    assert "_build_request_headers(" in source
    # Both call sites use the class helper, not the raw apply call.
    assert "self._build_request_headers(" in source
    # The class helper imports and uses apply_dify_headers_if_enabled.
    assert "from ._metadata import apply_dify_headers_if_enabled" in source


def test_build_request_headers_composes_bury_point_and_dify_headers(monkeypatch):
    # Class-level composition: the bury-point header from the existing
    # _get_market_bury_point_header method is preserved, and the Dify
    # request-metadata keys are merged on top.
    import dify_plugin

    from models.llm.llm import TongyiLargeLanguageModel

    class _FakeLLM(TongyiLargeLanguageModel):
        def __init__(self):
            pass

        def _get_market_bury_point_header(self, messages, extra_headers_str):
            return {"x-dashscope-euid": "bury-point-value"}

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    llm = _FakeLLM()
    headers = llm._build_request_headers(
        messages=[{"role": "user", "content": "hi"}],
        extra_headers_str="",
        credentials={"enable_request_metadata": "enabled"},
    )
    assert headers["x-dashscope-euid"] == "bury-point-value"
    assert headers["X-Dify-App-Id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert headers["X-Dify-Source"] == "dify"


def test_build_request_headers_omits_dify_keys_when_disabled():
    # When the opt-in is disabled, only the bury-point header remains.
    from models.llm.llm import TongyiLargeLanguageModel

    class _FakeLLM(TongyiLargeLanguageModel):
        def __init__(self):
            pass

        def _get_market_bury_point_header(self, messages, extra_headers_str):
            return {"x-dashscope-euid": "bury-point-value"}

    llm = _FakeLLM()
    headers = llm._build_request_headers(
        messages=[{"role": "user", "content": "hi"}],
        extra_headers_str="",
        credentials={"enable_request_metadata": "disabled"},
    )
    assert headers == {"x-dashscope-euid": "bury-point-value"}
    assert "X-Dify-App-Id" not in headers
    assert "X-Dify-Source" not in headers


def test_build_request_headers_omits_dify_keys_when_no_session():
    # When no Dify session is available, the bury-point header is the
    # sole content of the merged headers.
    from models.llm.llm import TongyiLargeLanguageModel

    class _FakeLLM(TongyiLargeLanguageModel):
        def __init__(self):
            pass

        def _get_market_bury_point_header(self, messages, extra_headers_str):
            return {"x-dashscope-euid": "bury-point-value"}

    llm = _FakeLLM()
    headers = llm._build_request_headers(
        messages=[{"role": "user", "content": "hi"}],
        extra_headers_str="",
        credentials={"enable_request_metadata": "enabled"},
    )
    assert headers == {"x-dashscope-euid": "bury-point-value"}
