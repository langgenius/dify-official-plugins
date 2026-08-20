from types import SimpleNamespace

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


def test_apply_noop_without_session_context():
    # Outside a Dify session, get_current_session() returns None rather than
    # raising, so no app_id resolves and target is left untouched.
    target: dict = {}
    apply_dify_metadata_if_enabled(target, {"enable_request_metadata": "enabled"})
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
    apply_dify_metadata_if_enabled(target, {"enable_request_metadata": "enabled"})
    assert "metadata" not in target
    assert "store" not in target


class _FakeSession:
    app_id = "550e8400-e29b-41d4-a716-446655440000"


def test_apply_merges_with_existing_metadata(monkeypatch):
    # When the target already carries a metadata dict (e.g. caller-supplied
    # values), Dify keys must merge into it rather than replace it wholesale.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    target: dict = {"metadata": {"user_supplied": "value"}}
    apply_dify_metadata_if_enabled(target, {"enable_request_metadata": "enabled"})
    assert target["metadata"]["user_supplied"] == "value"
    assert target["metadata"]["dify_app_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert target["metadata"]["dify_source"] == "dify"


def test_apply_replaces_non_dict_metadata(monkeypatch):
    # If existing metadata is somehow not a dict, Dify keys take over rather
    # than blow up — telemetry is best-effort.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    target: dict = {"metadata": "unexpected-string"}
    apply_dify_metadata_if_enabled(target, {"enable_request_metadata": "enabled"})
    assert isinstance(target["metadata"], dict)
    assert target["metadata"]["dify_app_id"] == "550e8400-e29b-41d4-a716-446655440000"


def test_apply_does_not_mutate_existing_metadata(monkeypatch):
    # The merge must not mutate the caller's dict in place: a shared reference
    # must never be modified as a side effect of telemetry opt-in.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    original = {"existing_key": "existing_value"}
    target: dict = {"metadata": original}
    apply_dify_metadata_if_enabled(target, {"enable_request_metadata": "enabled"})
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
    apply_dify_metadata_if_enabled(target, {"enable_request_metadata": "enabled"})
    assert target["store"] is True


def test_apply_skips_metadata_when_store_is_explicitly_false(monkeypatch):
    # An explicit store value set by the caller must be respected, not
    # overwritten. Because the API rejects metadata unless store is true,
    # respecting store=False also means skipping the metadata entirely rather
    # than emitting a request that is guaranteed to fail.
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    target: dict = {"store": False}
    apply_dify_metadata_if_enabled(target, {"enable_request_metadata": "enabled"})
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


# --- Wiring: the helper must be reached from both request builders. ---


def _enable(monkeypatch):
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    return {"enable_request_metadata": "enabled"}


def test_responses_parameters_attach_metadata_and_store(monkeypatch):
    from models.llm import responses

    params = responses.parameters("gpt-5.6", {}, None, None, _enable(monkeypatch))
    assert params["metadata"]["dify_app_id"] == _FakeSession.app_id
    assert params["metadata"]["dify_source"] == "dify"
    # The API only accepts metadata when store is enabled.
    assert params["store"] is True


def test_responses_parameters_keep_encrypted_reasoning_when_store_is_telemetry_only(
    monkeypatch,
):
    # store=true is forced solely to carry telemetry, so encrypted reasoning
    # passthrough must still be requested: opting in must not silently change
    # multi-turn reasoning behaviour.
    from models.llm import responses

    params = responses.parameters("gpt-5.6", {}, None, None, _enable(monkeypatch))
    assert params["store"] is True
    assert "reasoning.encrypted_content" in params["include"]


def test_responses_parameters_unchanged_when_disabled(monkeypatch):
    from models.llm import responses

    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    params = responses.parameters(
        "gpt-5.6", {}, None, None, {"enable_request_metadata": "disabled"}
    )
    assert "metadata" not in params
    assert params["store"] is False
    assert "reasoning.encrypted_content" in params["include"]


def test_responses_parameters_without_credentials_is_backward_compatible():
    # Existing call sites pass four positional arguments; credentials is
    # optional and its absence must behave exactly as before.
    from models.llm import responses

    params = responses.parameters("gpt-5.6", {}, None, None)
    assert "metadata" not in params
    assert params["store"] is False


def test_responses_parameters_respects_explicit_store_false(monkeypatch):
    # A caller-provided store=False cannot carry metadata, so telemetry is
    # skipped rather than producing a request the API rejects.
    from models.llm import responses

    params = responses.parameters(
        "gpt-5.6", {"store": False}, None, None, _enable(monkeypatch)
    )
    assert "metadata" not in params
    assert params["store"] is False


def _invoke_chat(mocker, credentials):
    from dify_plugin.entities.model.llm import LLMUsage
    from dify_plugin.entities.model.message import UserPromptMessage

    from models.llm import chat

    llm = mocker.Mock()
    llm._calc_response_usage.return_value = LLMUsage.empty_usage()
    client = mocker.Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        model="gpt-4o",
        system_fingerprint="fp",
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content="hi",
                    refusal=None,
                    function_call=None,
                    tool_calls=[],
                ),
            )
        ],
    )
    chat.generate_chat(
        llm,
        client,
        "gpt-4o",
        credentials,
        [UserPromptMessage(content="hello")],
        {},
        None,
        None,
        False,
        None,
    )
    return client.chat.completions.create.call_args.kwargs


def test_chat_params_attach_metadata_and_store(monkeypatch, mocker):
    sent = _invoke_chat(mocker, _enable(monkeypatch))
    assert sent["metadata"]["dify_app_id"] == _FakeSession.app_id
    assert sent["metadata"]["dify_source"] == "dify"
    assert sent["store"] is True


def test_chat_params_unchanged_when_disabled(monkeypatch, mocker):
    import dify_plugin

    monkeypatch.setattr(dify_plugin, "get_current_session", lambda: _FakeSession())
    sent = _invoke_chat(mocker, {"enable_request_metadata": "disabled"})
    assert "metadata" not in sent
    assert "store" not in sent
