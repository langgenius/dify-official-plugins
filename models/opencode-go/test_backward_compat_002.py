"""Backward-compat: 0.0.2 users must keep identical auto-session behavior.

0.0.3 only *adds* LLM-node extra_headers; when that parameter is absent,
session generation and credential handling must match 0.0.2.
"""
from unittest.mock import MagicMock, patch

from dify_plugin.entities.model.message import SystemPromptMessage, UserPromptMessage
from dify_plugin.errors.model import InvokeError

from models.llm.llm import OpenCodeGoLargeLanguageModel


def _prompt_messages():
    return [
        SystemPromptMessage(content="You are a helpful assistant."),
        UserPromptMessage(content="Hello"),
    ]


def _capture_invoke(credentials, model_parameters, user=None, session=None):
    """Invoke with super() patched; return (credentials, model_parameters)."""
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(
        self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user
    ):
        captured["credentials"] = dict(credentials)
        captured["model_parameters"] = dict(model_parameters)
        return iter([])

    patch_target = (
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke"
    )
    session_patch = patch("models.llm.llm.get_current_session", return_value=session)
    with patch(patch_target, new=fake_super), session_patch:
        model._invoke(
            model="mimo-v2.5",
            credentials=credentials,
            prompt_messages=_prompt_messages(),
            model_parameters=model_parameters,
            stream=True,
            user=user,
        )
    return captured["credentials"], captured["model_parameters"]


# ---------------------------------------------------------------------------
# Schema: 0.0.2 parameters still present; extra_headers is optional
# ---------------------------------------------------------------------------

def test_schema_keeps_002_parameters():
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    schema = model.get_customizable_model_schema(
        "mimo-v2.5", {"mode": "chat", "context_size": "262144", "max_tokens": "8192"}
    )
    names = {rule.name for rule in schema.parameter_rules}
    assert {"temperature", "top_p", "max_tokens"}.issubset(names)
    assert "extra_headers" in names
    by_name = {rule.name: rule for rule in schema.parameter_rules}
    assert by_name["extra_headers"].required is True
    assert by_name["extra_headers"].default
    assert by_name["max_tokens"].max == 8192
    assert by_name["temperature"].type.value == "number" or by_name[
        "temperature"
    ].type.value == "float"


# ---------------------------------------------------------------------------
# No extra_headers in model_parameters (the 0.0.2 upgrade path)
# ---------------------------------------------------------------------------

def test_no_extra_headers_leaves_model_parameters_untouched():
    creds, params = _capture_invoke(
        credentials={"api_key": "sk-test", "mode": "chat"},
        model_parameters={"max_tokens": 64, "temperature": 0.1},
        user="20162097",
    )
    assert "extra_headers" not in params
    assert params["max_tokens"] == 64
    assert params["temperature"] == 0.1
    assert creds["extra_headers"]["User-Agent"].startswith("dify-opencode-go-plugin/")
    # Unchecked extra_headers → per-invoke random, never sticky user.
    assert creds["extra_headers"]["x-opencode-session"] != "20162097"
    assert creds["extra_headers"]["x-opencode-session"]
    assert creds["mode"] == "chat"
    assert creds["endpoint_url"] == "https://opencode.ai/zen/go/v1"


def test_no_extra_headers_same_user_not_sticky():
    sessions = []
    for _ in range(3):
        creds, _ = _capture_invoke(
            credentials={"api_key": "sk-test"},
            model_parameters={},
            user="20162097",
            session=None,
        )
        sessions.append(creds["extra_headers"]["x-opencode-session"])
    assert sessions[0] != sessions[1]
    assert "20162097" not in sessions[0]


def test_no_extra_headers_conversation_still_preferred():
    session = MagicMock()
    session.conversation_id = "conv-legacy-002"
    creds, _ = _capture_invoke(
        credentials={"api_key": "sk-test"},
        model_parameters={},
        user="20162097",
        session=session,
    )
    sid = creds["extra_headers"]["x-opencode-session"]
    assert sid == "conv-legacy-002"
    assert "20162097" not in sid


def test_credential_session_id_still_overrides_auto():
    creds, _ = _capture_invoke(
        credentials={"api_key": "sk-test", "session_id": "custom-fixed"},
        model_parameters={},
        user="20162097",
    )
    assert creds["extra_headers"]["x-opencode-session"] == "custom-fixed"


def test_user_agent_credential_still_respected():
    creds, _ = _capture_invoke(
        credentials={"api_key": "sk-test", "user_agent": "my-custom-agent/9"},
        model_parameters={},
        user="u-1",
    )
    assert creds["extra_headers"]["User-Agent"] == "my-custom-agent/9"


def test_empty_extra_headers_string_is_noop():
    creds, params = _capture_invoke(
        credentials={"api_key": "sk-test"},
        model_parameters={"extra_headers": "", "max_tokens": 8},
        user="20162097",
    )
    assert "extra_headers" not in params
    assert creds["extra_headers"]["x-opencode-session"] != "20162097"


def test_extra_headers_none_is_noop():
    creds, _ = _capture_invoke(
        credentials={"api_key": "sk-test"},
        model_parameters={"extra_headers": None},
        user="20162097",
    )
    assert creds["extra_headers"]["x-opencode-session"] != "20162097"


# ---------------------------------------------------------------------------
# Pre-existing credentials.extra_headers (dict or JSON string)
# ---------------------------------------------------------------------------

def test_credential_extra_headers_dict_preserved():
    creds, _ = _capture_invoke(
        credentials={
            "api_key": "sk-test",
            "extra_headers": {"x-tenant": "yili"},
        },
        model_parameters={},
        user="20162097",
    )
    assert creds["extra_headers"]["x-tenant"] == "yili"
    assert creds["extra_headers"]["x-opencode-session"] != "20162097"
    assert creds["extra_headers"]["x-opencode-session"]


def test_credential_extra_headers_json_string_preserved():
    creds, _ = _capture_invoke(
        credentials={
            "api_key": "sk-test",
            "extra_headers": '{"x-tenant": "yili"}',
        },
        model_parameters={},
        user="20162097",
    )
    assert creds["extra_headers"]["x-tenant"] == "yili"
    assert creds["extra_headers"]["x-opencode-session"] != "20162097"


def test_node_headers_merge_over_credential_headers():
    creds, _ = _capture_invoke(
        credentials={
            "api_key": "sk-test",
            "extra_headers": {"x-tenant": "yili", "x-opencode-session": "cred-level"},
        },
        model_parameters={
            "extra_headers": '{"x-opencode-session": "node-run-id", "x-trace": "t1"}',
        },
        user="20162097",
    )
    # node wins on conflicts; credential-only keys kept
    assert creds["extra_headers"]["x-tenant"] == "yili"
    assert creds["extra_headers"]["x-trace"] == "t1"
    assert creds["extra_headers"]["x-opencode-session"] == "node-run-id"


def test_node_headers_without_session_keep_credential_session():
    creds, _ = _capture_invoke(
        credentials={
            "api_key": "sk-test",
            "extra_headers": {"x-opencode-session": "cred-level"},
        },
        model_parameters={
            "extra_headers": '{"x-trace": "t1"}',
        },
        user="20162097",
    )
    assert creds["extra_headers"]["x-trace"] == "t1"
    assert creds["extra_headers"]["x-opencode-session"] == "cred-level"


def test_static_credential_session_id_not_applied_when_node_sets_session():
    """Documented precedence: node extra_headers beat credential session_id."""
    creds, _ = _capture_invoke(
        credentials={"api_key": "sk-test", "session_id": "cred-session"},
        model_parameters={
            "extra_headers": '{"x-opencode-session": "node-run"}',
        },
        user="20162097",
    )
    assert creds["extra_headers"]["x-opencode-session"] == "node-run"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_invalid_extra_headers_raises():
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    try:
        model._invoke(
            model="mimo-v2.5",
            credentials={"api_key": "sk-test"},
            prompt_messages=_prompt_messages(),
            model_parameters={"extra_headers": "{bad"},
            stream=True,
        )
        raise AssertionError("expected InvokeError")
    except InvokeError as exc:
        assert "extra_headers" in str(exc)


def test_extra_headers_non_object_json_raises():
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    try:
        model._invoke(
            model="mimo-v2.5",
            credentials={"api_key": "sk-test"},
            prompt_messages=_prompt_messages(),
            model_parameters={"extra_headers": '["a"]'},
            stream=True,
        )
        raise AssertionError("expected InvokeError")
    except InvokeError:
        pass


# ---------------------------------------------------------------------------
# validate_credentials / schema paths still work (0.0.2 call sites)
# ---------------------------------------------------------------------------

def test_validate_credentials_still_builds_headers():
    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    credentials = {"api_key": "sk-test", "endpoint_url": "https://example.test/v1"}

    def fake_validate(self, model, credentials):
        assert credentials["extra_headers"]["User-Agent"].startswith(
            "dify-opencode-go-plugin/"
        )
        assert credentials["extra_headers"]["x-opencode-session"]
        assert "anon-" not in credentials["extra_headers"]["x-opencode-session"]
        return True

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel.validate_credentials",
        new=fake_validate,
    ), patch("models.llm.llm.get_current_session", return_value=None):
        model.validate_credentials(model="mimo-v2.5", credentials=credentials)


def test_get_customizable_model_schema_still_works():
    from dify_plugin.entities.model import ModelPropertyKey

    model = OpenCodeGoLargeLanguageModel(model_schemas=[])
    schema = model.get_customizable_model_schema(
        "kimi-k2.6", {"mode": "chat", "context_size": "131072"}
    )
    assert schema.model == "kimi-k2.6"
    assert schema.model_properties[ModelPropertyKey.MODE] == "chat"


if __name__ == "__main__":
    tests = [
        test_schema_keeps_002_parameters,
        test_no_extra_headers_leaves_model_parameters_untouched,
        test_no_extra_headers_same_user_not_sticky,
        test_no_extra_headers_conversation_still_preferred,
        test_credential_session_id_still_overrides_auto,
        test_user_agent_credential_still_respected,
        test_empty_extra_headers_string_is_noop,
        test_extra_headers_none_is_noop,
        test_credential_extra_headers_dict_preserved,
        test_credential_extra_headers_json_string_preserved,
        test_node_headers_merge_over_credential_headers,
        test_node_headers_without_session_keep_credential_session,
        test_static_credential_session_id_not_applied_when_node_sets_session,
        test_invalid_extra_headers_raises,
        test_extra_headers_non_object_json_raises,
        test_validate_credentials_still_builds_headers,
        test_get_customizable_model_schema_still_works,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\nDONE failed={failed}")
    raise SystemExit(1 if failed else 0)
