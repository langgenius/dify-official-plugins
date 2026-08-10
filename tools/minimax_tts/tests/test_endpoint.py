"""In-process tests for MiniMax TTS endpoint selection (pytest-shaped).

Fails before this change: both t2a_v2 call sites hardcoded the legacy
api.minimax.chat host; keys from MiniMax's current china (api.minimaxi.com)
and international (api.minimax.io) platforms had no way in."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PLUGIN_ROOT = _HERE.parent
sys.path.insert(0, str(_PLUGIN_ROOT))

from utils.endpoint import get_base_url  # noqa: E402


def test_default_is_byte_identical_legacy():
    # absent / empty / unknown values all resolve to the exact host every
    # existing installation used before this change
    for creds in ({}, {"api_endpoint": ""}, {"api_endpoint": "bogus"}):
        assert get_base_url(creds) == "https://api.minimax.chat"


def test_documented_current_hosts():
    assert get_base_url({"api_endpoint": "china"}) == "https://api.minimaxi.com"
    assert get_base_url({"api_endpoint": "international"}) == "https://api.minimax.io"


def test_no_hardcoded_host_left_in_api_calls():
    for sub in ("provider", "tools"):
        for py in (_PLUGIN_ROOT / sub).glob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    assert not node.value.startswith("https://api.minimax"), (
                        f"hardcoded API host in {py.name}:{node.lineno}"
                    )
                if isinstance(node, ast.JoinedStr):
                    for part in node.values:
                        if isinstance(part, ast.Constant) and isinstance(part.value, str):
                            assert "api.minimax.chat" not in part.value, (
                                f"hardcoded host in f-string {py.name}:{node.lineno}"
                            )
