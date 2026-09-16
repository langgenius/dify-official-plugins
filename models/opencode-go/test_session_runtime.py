"""Local verification for per-conversation x-opencode-session (no network)."""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from dify_plugin.core.runtime import Session
from dify_plugin.core.server.tcp.request_reader import TCPReaderWriter

from models.llm.llm import OpenCodeGoLargeLanguageModel


def make_real_session(conversation_id):
    return Session(
        session_id="plugin-rpc-session",
        executor=ThreadPoolExecutor(max_workers=1),
        reader=TCPReaderWriter(host="127.0.0.1", port=1, key="k"),
        writer=TCPReaderWriter(host="127.0.0.1", port=1, key="k"),
        conversation_id=conversation_id,
        message_id="msg-1",
        app_id="app-1",
    )


def test_header_prefers_real_session_conversation() -> None:
    session = make_real_session("11111111-2222-3333-4444-555555555555")
    credentials: dict = {"api_key": "sk-test"}
    with patch("models.llm.llm.get_current_session", return_value=session):
        OpenCodeGoLargeLanguageModel._add_custom_parameters(credentials, user="user-9")
    sid = credentials["extra_headers"]["x-opencode-session"]
    assert sid == "11111111-2222-3333-4444-555555555555"
    assert "user-9" not in sid
    assert credentials["extra_headers"]["User-Agent"].startswith("dify-opencode-go-plugin/")


def test_same_conversation_stable_across_calls() -> None:
    session = make_real_session("conv-stable-001")
    a = {}
    b = {}
    with patch("models.llm.llm.get_current_session", return_value=session):
        OpenCodeGoLargeLanguageModel._add_custom_parameters(a, user="u")
        OpenCodeGoLargeLanguageModel._add_custom_parameters(b, user="u")
    assert (
        a["extra_headers"]["x-opencode-session"]
        == b["extra_headers"]["x-opencode-session"]
    )


def test_two_conversations_different_sessions() -> None:
    s1 = make_real_session("conv-alpha")
    s2 = make_real_session("conv-beta")
    c1: dict = {}
    c2: dict = {}
    with patch("models.llm.llm.get_current_session", return_value=s1):
        OpenCodeGoLargeLanguageModel._add_custom_parameters(c1, user="same-user")
    with patch("models.llm.llm.get_current_session", return_value=s2):
        OpenCodeGoLargeLanguageModel._add_custom_parameters(c2, user="same-user")
    assert (
        c1["extra_headers"]["x-opencode-session"]
        != c2["extra_headers"]["x-opencode-session"]
    )


def test_empty_conversation_falls_back_to_rpc_session() -> None:
    session = make_real_session("")  # Agent / completion without conversation
    credentials: dict = {}
    with patch("models.llm.llm.get_current_session", return_value=session):
        OpenCodeGoLargeLanguageModel._add_custom_parameters(credentials, user="20162097")
    sid = credentials["extra_headers"]["x-opencode-session"]
    # Prefer per-invocation RPC session over sticky user so new chats isolate.
    assert sid == "plugin-rpc-session"
    assert "20162097" not in sid


def test_none_session_falls_back_to_random() -> None:
    credentials: dict = {}
    with patch("models.llm.llm.get_current_session", return_value=None):
        OpenCodeGoLargeLanguageModel._add_custom_parameters(credentials, user="abc-user")
    sid = credentials["extra_headers"]["x-opencode-session"]
    assert sid != "abc-user"
    assert sid


def test_explicit_credential_overrides_everything() -> None:
    session = make_real_session("conv-should-be-ignored")
    credentials: dict = {"session_id": "fixed-by-admin"}
    with patch("models.llm.llm.get_current_session", return_value=session):
        OpenCodeGoLargeLanguageModel._add_custom_parameters(credentials, user="u")
    assert credentials["extra_headers"]["x-opencode-session"] == "fixed-by-admin"


def test_special_chars_in_conversation_sanitized() -> None:
    session = make_real_session("conv/with spaces:and*bad")
    credentials: dict = {}
    with patch("models.llm.llm.get_current_session", return_value=session):
        OpenCodeGoLargeLanguageModel._add_custom_parameters(credentials, user="u")
    sid = credentials["extra_headers"]["x-opencode-session"]
    assert " " not in sid and "*" not in sid and ":" not in sid
    assert "conv" in sid


def test_validate_credentials_path_no_crash() -> None:
    # validate_credentials uses user=None and usually no conversation
    credentials: dict = {"api_key": "sk-test"}
    with patch("models.llm.llm.get_current_session", return_value=None):
        OpenCodeGoLargeLanguageModel._add_custom_parameters(credentials, user=None)
    assert credentials["extra_headers"]["x-opencode-session"]


def test_dify_session_context_var_integration() -> None:
    """Use dify_plugin's real use_current_session context manager."""
    from dify_plugin.core.session_context import use_current_session

    session = make_real_session("ctxvar-conv-42")
    credentials: dict = {}
    # Do not patch get_current_session — rely on real ContextVar wiring
    with use_current_session(session):
        OpenCodeGoLargeLanguageModel._add_custom_parameters(credentials, user="u")
    assert credentials["extra_headers"]["x-opencode-session"] == "ctxvar-conv-42"


if __name__ == "__main__":
    tests = [
        test_header_prefers_real_session_conversation,
        test_same_conversation_stable_across_calls,
        test_two_conversations_different_sessions,
        test_empty_conversation_falls_back_to_rpc_session,
        test_none_session_falls_back_to_random,
        test_explicit_credential_overrides_everything,
        test_special_chars_in_conversation_sanitized,
        test_validate_credentials_path_no_crash,
        test_dify_session_context_var_integration,
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
