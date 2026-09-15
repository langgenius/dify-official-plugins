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
    with patch(
        "models.llm.llm.get_current_session", return_value=mock_session
    ):
        a = OpenCodeGoLargeLanguageModel._build_session_id("user-1", {})
        b = OpenCodeGoLargeLanguageModel._build_session_id("user-1", {})
    assert a == b
    assert a.endswith("/conv-abc-123")
    assert "user-1" not in a


def test_different_conversations_differ() -> None:
    s1 = MagicMock(conversation_id="conv-one")
    s2 = MagicMock(conversation_id="conv-two")
    with patch("models.llm.llm.get_current_session", return_value=s1):
        a = OpenCodeGoLargeLanguageModel._build_session_id("user-1", {})
    with patch("models.llm.llm.get_current_session", return_value=s2):
        b = OpenCodeGoLargeLanguageModel._build_session_id("user-1", {})
    assert a != b
    assert a.endswith("/conv-one")
    assert b.endswith("/conv-two")


def test_fallback_without_conversation() -> None:
    with patch("models.llm.llm.get_current_session", return_value=None):
        a = OpenCodeGoLargeLanguageModel._build_session_id("20162097", {})
        b = OpenCodeGoLargeLanguageModel._build_session_id("20162097", {})
        c = OpenCodeGoLargeLanguageModel._build_session_id("other-user", {})
    assert a == b
    assert a != c
    assert a.endswith("/20162097")


def test_short_user_anon_fallback() -> None:
    with patch("models.llm.llm.get_current_session", return_value=None):
        sid = OpenCodeGoLargeLanguageModel._build_session_id("x", {})
    assert "anon-" in sid


if __name__ == "__main__":
    test_explicit_session_override()
    test_conversation_id_preferred()
    test_different_conversations_differ()
    test_fallback_without_conversation()
    test_short_user_anon_fallback()
    print("session_id tests OK")
