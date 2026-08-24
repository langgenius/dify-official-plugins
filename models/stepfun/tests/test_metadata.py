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
    # Visible ASCII punctuation is preserved; only CR/LF and other
    # control characters are stripped.
    assert normalize_header_value("a[b]c") == "a[b]c"


def test_normalize_strips_non_ascii():
    # Non-ASCII characters are dropped so urllib3 never rejects the
    # header. The visible-ASCII restriction also catches surrogate
    # code points and other invalid UTF-16 sequences.
    assert normalize_header_value("日本語") == ""
    assert normalize_header_value("café") == "caf"


def test_normalize_strips_cr_lf_and_control_chars():
    # CR/LF and other control characters would cause urllib3 to raise
    # InvalidHeader on outbound requests. They are stripped.
    assert normalize_header_value("a\nb") == "ab"
    assert normalize_header_value("a\rb") == "ab"
    assert normalize_header_value("a\r\nb") == "ab"
    assert normalize_header_value("a\x00b") == "ab"
    assert normalize_header_value("a\x1fb") == "ab"  # unit separator


def test_normalize_strips_whitespace_only_to_empty():
    # Whitespace-only inputs collapse to empty so build_dify_headers
    # can skip injection rather than attach a useless header.
    assert normalize_header_value("   ") == ""
    assert normalize_header_value("\t\n") == ""
    assert normalize_header_value(" \r\n ") == ""


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
    # Non-string inputs are stringified before validation, so a numeric 0
    # (falsy) does not get dropped by the empty-check.
    assert normalize_header_value(0) == "0"
    assert normalize_header_value(123) == "123"


# --- build_dify_headers ---


def test_build_dify_headers_returns_none_for_none():
    assert build_dify_headers(None) is None


def test_build_dify_headers_returns_none_for_empty():
    assert build_dify_headers("") is None


def test_build_dify_headers_keeps_non_string_falsy():
    # build_dify_headers only rejects None and "" — other falsy values
    # such as numeric 0 are coerced by normalize_header_value.
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


def test_apply_returns_new_credentials_when_credential_missing():
    credentials: dict = {"api_key": "k", "endpoint_url": "https://x"}
    result = apply_dify_headers_if_enabled(credentials)
    # The function always returns a new dict (no-mutation contract),
    # even when the feature is disabled.
    assert result is not credentials
    assert result == credentials
    assert "extra_headers" not in credentials
    # Original dict is not mutated.
    assert "extra_headers" not in credentials or credentials.get("extra_headers") is None


def test_apply_returns_same_credentials_when_credential_disabled():
    credentials: dict = {
        "api_key": "k",
        "endpoint_url": "https://x",
        "enable_request_metadata": "disabled",
    }
    result = apply_dify_headers_if_enabled(credentials)
    assert result is not credentials
    assert result == credentials
    assert "extra_headers" not in result
    # Original dict is not mutated.
    assert "extra_headers" not in credentials


def test_apply_noop_without_session_context():
    # Outside a Dify session, get_current_session() returns None rather
    # than raising, so no app_id resolves. A new credentials dict is
    # returned without extra_headers, matching the disabled path.
    credentials: dict = {
        "api_key": "k",
        "endpoint_url": "https://x",
        "enable_request_metadata": "enabled",
    }
    result = apply_dify_headers_if_enabled(credentials)
    assert result is not credentials
    assert "extra_headers" not in result
    assert "extra_headers" not in credentials


def test_apply_silent_when_session_lookup_raises(monkeypatch):
    # Telemetry must never break generation, so a raising session lookup
    # is swallowed. Exercises the except branch directly, which the
    # None-returning path above cannot reach.
    import dify_plugin

    def _boom():
        raise RuntimeError("session backend unavailable")

    monkeypatch.setattr(dify_plugin, "get_current_session", _boom)
    credentials: dict = {
        "api_key": "k",
        "endpoint_url": "https://x",
        "enable_request_metadata": "enabled",
    }
    result = apply_dify_headers_if_enabled(credentials)
    assert result is not credentials
    assert "extra_headers" not in result


class _FakeSession:
    app_id = "550e8400-e29b-41d4-a716-446655440000"


# --- apply_dify_headers_if_enabled: header composition ---


def test_apply_merges_with_existing_extra_headers(monkeypatch):
    # When credentials already carry extra_headers (e.g. caller-supplied
    # values), Dify keys must merge in rather than replace the whole dict.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    credentials: dict = {
        "api_key": "k",
        "endpoint_url": "https://x",
        "enable_request_metadata": "enabled",
        "extra_headers": {"X-Existing": "value"},
    }
    result = apply_dify_headers_if_enabled(credentials)
    # Returned dict is a new shallow copy, not the original.
    assert result is not credentials
    assert result["extra_headers"]["X-Existing"] == "value"
    assert result["extra_headers"]["X-Dify-App-Id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert result["extra_headers"]["X-Dify-Source"] == "dify"
    # Original credentials are not mutated.
    assert "X-Dify-App-Id" not in credentials["extra_headers"]


def test_apply_replaces_non_dict_extra_headers(monkeypatch):
    # If existing extra_headers is somehow not a dict, Dify keys take
    # over rather than blow up — telemetry is best-effort.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    credentials: dict = {
        "api_key": "k",
        "endpoint_url": "https://x",
        "enable_request_metadata": "enabled",
        "extra_headers": "unexpected-string",
    }
    result = apply_dify_headers_if_enabled(credentials)
    assert isinstance(result["extra_headers"], dict)
    assert result["extra_headers"]["X-Dify-App-Id"] == "550e8400-e29b-41d4-a716-446655440000"


def test_apply_does_not_mutate_existing_extra_headers(monkeypatch):
    # The merge must not mutate the caller's dict in place: a shared
    # reference must never be modified as a side effect of telemetry
    # opt-in.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    original = {"X-Existing": "value"}
    credentials: dict = {
        "api_key": "k",
        "endpoint_url": "https://x",
        "enable_request_metadata": "enabled",
        "extra_headers": original,
    }
    result = apply_dify_headers_if_enabled(credentials)
    # Original dict is left untouched.
    assert original == {"X-Existing": "value"}
    # Returned credentials carry a new, merged dict.
    assert result["extra_headers"] is not original
    assert result["extra_headers"]["X-Existing"] == "value"
    assert result["extra_headers"]["X-Dify-App-Id"] == "550e8400-e29b-41d4-a716-446655440000"


def test_apply_writes_extra_headers_when_credentials_empty(monkeypatch):
    # With no prior extra_headers, apply should write a fresh dict
    # carrying only the Dify keys.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    credentials: dict = {
        "api_key": "k",
        "endpoint_url": "https://x",
        "enable_request_metadata": "enabled",
    }
    result = apply_dify_headers_if_enabled(credentials)
    assert result["extra_headers"] == {
        "X-Dify-App-Id": "550e8400-e29b-41d4-a716-446655440000",
        "X-Dify-Source": "dify",
    }
    # The original credentials dict is not mutated.
    assert "extra_headers" not in credentials


def test_apply_dify_keys_override_caller_keys_on_collision(monkeypatch):
    # When the caller already supplies a key that the helper also writes,
    # the helper's value wins — telemetry is the explicit purpose of the
    # helper, and a caller-side X-Dify-App-Id is most likely stale.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    credentials: dict = {
        "api_key": "k",
        "endpoint_url": "https://x",
        "enable_request_metadata": "enabled",
        "extra_headers": {"X-Dify-App-Id": "stale-value"},
    }
    result = apply_dify_headers_if_enabled(credentials)
    assert result["extra_headers"]["X-Dify-App-Id"] == "550e8400-e29b-41d4-a716-446655440000"


def test_apply_drops_caller_keys_with_lowercase_collision(monkeypatch):
    # HTTP header names are case-insensitive. If the caller supplies
    # "x-dify-app-id" (lowercase), the merge must drop it so the upstream
    # request carries exactly one header per logical name, not two
    # case-variants.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    credentials: dict = {
        "api_key": "k",
        "endpoint_url": "https://x",
        "enable_request_metadata": "enabled",
        "extra_headers": {
            "x-dify-app-id": "stale-lowercase",
            "X-DIFY-APP-ID": "stale-uppercase",
            "X-Dify-Source": "stale-source",
            "X-Other-Header": "preserved",
        },
    }
    result = apply_dify_headers_if_enabled(credentials)
    # Only the canonical-case Dify keys remain; the case-variants of
    # the same logical name are dropped.
    assert result["extra_headers"]["X-Dify-App-Id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert result["extra_headers"]["X-Dify-Source"] == "dify"
    assert "x-dify-app-id" not in result["extra_headers"]
    assert "X-DIFY-APP-ID" not in result["extra_headers"]
    # Non-colliding caller keys are preserved.
    assert result["extra_headers"]["X-Other-Header"] == "preserved"


def test_build_dify_headers_returns_none_for_whitespace_only_app_id(monkeypatch):
    # If the session returns a whitespace-only app_id (or one that
    # normalizes to empty), the helper must skip header injection
    # rather than emit a useless X-Dify-App-Id header.
    import dify_plugin

    class _WhitespaceSession:
        app_id = "   "

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _WhitespaceSession())
    credentials: dict = {
        "api_key": "k",
        "endpoint_url": "https://x",
        "enable_request_metadata": "enabled",
    }
    result = apply_dify_headers_if_enabled(credentials)
    assert "extra_headers" not in result


def test_build_dify_headers_returns_none_for_app_id_with_only_control_chars(monkeypatch):
    # If the session returns an app_id with only control characters,
    # the helper must skip header injection rather than emit a header
    # that urllib3 would reject.
    import dify_plugin

    class _ControlOnlySession:
        app_id = "\n\r\x00"

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _ControlOnlySession())
    credentials: dict = {
        "api_key": "k",
        "endpoint_url": "https://x",
        "enable_request_metadata": "enabled",
    }
    result = apply_dify_headers_if_enabled(credentials)
    assert "extra_headers" not in result


# --- apply_dify_headers_if_enabled: source-level guard ---


def test_llm_module_uses_dify_headers_helper():
    # The wiring in llm.py must reach apply_dify_headers_if_enabled so the
    # opt-in credential is honored on the request path. A source-level
    # guard catches accidental removal during refactors of the call site.
    import inspect

    from models.llm import llm as llm_module

    source = inspect.getsource(llm_module)
    assert "apply_dify_headers_if_enabled(credentials)" in source
    assert "from ._metadata import apply_dify_headers_if_enabled" in source
