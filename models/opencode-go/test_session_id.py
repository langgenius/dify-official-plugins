"""Unit tests for x-opencode-session generation (no network)."""
from unittest.mock import MagicMock, patch

from models.llm.llm import OpenCodeGoLargeLanguageModel


def test_explicit_session_override() -> None:
    sid = OpenCodeGoLargeLanguageModel._build_session_id(
        "user-1", {"session_id": "custom-fixed"}
    )
    assert sid == "custom-fixed"


def test_conversation_id_preferred() -> None:
    mock_session = MagicMock()
    mock_session.conversation_id = "conv-abc-123"
    mock_session.session_id = "rpc-xyz"
    with patch(
        "models.llm.llm.get_current_session", return_value=mock_session
    ):
        a = OpenCodeGoLargeLanguageModel._build_session_id("user-1", {})
        b = OpenCodeGoLargeLanguageModel._build_session_id("user-1", {})
    assert a == b
    # Bare Dify conversation id — OpenCode only needs a stable session string.
    assert a == "conv-abc-123"
    assert "user-1" not in a


def test_different_conversations_differ() -> None:
    s1 = MagicMock(conversation_id="conv-one", session_id="rpc-1")
    s2 = MagicMock(conversation_id="conv-two", session_id="rpc-2")
    with patch("models.llm.llm.get_current_session", return_value=s1):
        a = OpenCodeGoLargeLanguageModel._build_session_id("user-1", {})
    with patch("models.llm.llm.get_current_session", return_value=s2):
        b = OpenCodeGoLargeLanguageModel._build_session_id("user-1", {})
    assert a == "conv-one"
    assert b == "conv-two"
    assert a != b


def test_fallback_without_conversation() -> None:
    with patch("models.llm.llm.get_current_session", return_value=None):
        a = OpenCodeGoLargeLanguageModel._build_session_id("20162097", {})
        b = OpenCodeGoLargeLanguageModel._build_session_id("20162097", {})
        c = OpenCodeGoLargeLanguageModel._build_session_id("other-user", {})
    # Unchecked extra_headers / missing conversation → per-invoke random, not user.
    assert a != b
    assert a != c
    assert "20162097" not in a
    assert "other-user" not in c


def test_short_user_anon_fallback() -> None:
    with patch("models.llm.llm.get_current_session", return_value=None):
        sid = OpenCodeGoLargeLanguageModel._build_session_id("x", {})
    assert "anon-" not in sid
    assert sid


if __name__ == "__main__":
    test_explicit_session_override()
    test_conversation_id_preferred()
    test_different_conversations_differ()
    test_fallback_without_conversation()
    test_short_user_anon_fallback()
    print("session_id tests OK")
