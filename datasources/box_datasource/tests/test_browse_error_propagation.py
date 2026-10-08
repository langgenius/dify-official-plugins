"""Regression tests for the Box browse error-swallowing bug fixed in this PR.

Before the fix, the catch-all `except Exception` at the bottom of
`_browse_files` returned `OnlineDriveBrowseFilesResponse(result=[])`
for every non-401 error. Combined with the pre-existing 'if not items:
return empty' branch at the top of the try block, this made a Box API
404 / 500 / unexpected KeyError indistinguishable from a genuinely
empty folder — the user saw 'no items' with no diagnostic pointing at
the failure.

These tests pin:

  * a 401 response raises the auth guidance message (preserved);
  * a 404 response raises a folder-not-found error (already explicit,
    pre-fix);
  * a 500 response raises an HTTP error (already explicit, pre-fix);
  * a successful response with an empty `entries` list returns an
    empty bucket (the legitimate 'folder is empty' signal — preserved);
  * a successful response with a KeyError on an unexpected field
    raises instead of returning empty (the new behavior);
  * a successful response that triggers a connection error raises
    a 'Network error' message (already explicit, pre-fix, but covered
    to prevent regression);
  * a source-level guard pins the dispatcher on box.py so a future
    refactor can't reintroduce `return OnlineDriveBrowseFilesResponse(result=[])`
    inside the catch-all.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
import requests

from datasources.box import BoxDataSource

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST_PY = PLUGIN_ROOT / "datasources" / "box.py"


# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Stand-in for requests.Response with .json(), .status_code, and .text."""

    def __init__(self, payload: dict[str, Any] | None = None, status_code: int = 200, text: str = "") -> None:
        self._payload = payload or {}
        self.status_code = status_code
        self.text = text

    def json(self) -> dict[str, Any]:
        return self._payload


class _RuntimeStub:
    def __init__(self) -> None:
        self.credentials = {"access_token": "box-test-token"}


def _instance() -> BoxDataSource:
    obj = BoxDataSource.__new__(BoxDataSource)
    obj.runtime = _RuntimeStub()
    return obj


def _drive_browse_request(folder_id: str = "0"):
    from dify_plugin.entities.datasource import OnlineDriveBrowseFilesRequest
    return OnlineDriveBrowseFilesRequest(
        bucket="box",
        prefix=folder_id,
        max_keys=10,
        next_page_parameters={},
    )


def _run_browse(monkeypatch: pytest.MonkeyPatch, *, response: _FakeResponse | Exception):
    """Drive _browse_files end-to-end with the fake response."""
    instance = _instance()

    def fake_get(url: str, headers: Any = None, params: Any = None, timeout: Any = None):
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("datasources.box.requests.get", fake_get)
    return instance._browse_files(_drive_browse_request())


# ---------------------------------------------------------------------------
# Error-propagation behavior
# ---------------------------------------------------------------------------

def test_404_raises_folder_not_found(monkeypatch: pytest.MonkeyPatch):
    """Pre-existing 404 behavior is preserved (raised as ValueError, not returned as empty)."""
    with pytest.raises(ValueError, match="Folder with ID '0' not found"):
        _run_browse(monkeypatch, response=_FakeResponse(status_code=404, text="not found"))


def test_500_raises_http_error(monkeypatch: pytest.MonkeyPatch):
    """Pre-existing 500 behavior is preserved (raised as ValueError, not returned as empty)."""
    with pytest.raises(ValueError, match="Failed to list files: 500"):
        _run_browse(monkeypatch, response=_FakeResponse(status_code=500, text="server error"))


def test_401_raises_auth_guidance(monkeypatch: pytest.MonkeyPatch):
    """Pre-existing 401 behavior is preserved with the auth guidance message."""
    with pytest.raises(ValueError, match="Authentication failed"):
        _run_browse(monkeypatch, response=_FakeResponse(status_code=401, text="unauthorized"))


def test_401_via_unauthorized_string_raises_auth_guidance(monkeypatch: pytest.MonkeyPatch):
    """Pre-existing 401 fallback via the 'Unauthorized' string match is preserved."""
    # A 200 response that nevertheless surfaces 'Unauthorized' in an exception.
    class _UnauthorizedException(Exception):
        def __str__(self) -> str:
            return "Box returned Unauthorized"

    with pytest.raises(ValueError, match="Authentication failed.*Please refresh or reauthorize"):
        _run_browse(monkeypatch, response=_UnauthorizedException())


def test_empty_folder_with_successful_response_returns_empty_bucket(monkeypatch: pytest.MonkeyPatch):
    """A genuine 200 + empty `entries` is the legitimate 'folder is empty' signal — must still return an empty bucket."""
    response = _run_browse(
        monkeypatch,
        response=_FakeResponse(payload={"entries": [], "total_count": 0, "offset": 0, "limit": 10}),
    )
    # The response shape: a single bucket with no files, not an error.
    assert response.result == []
    # Crucially: no exception was raised.


def test_keyerror_on_unexpected_response_field_raises(monkeypatch: pytest.MonkeyPatch):
    """Issue #3980 repro: a successful response that surprises the parser must raise, not silently return empty.

    The fix's catch-all re-raises any non-401 exception instead of returning empty.
    Concretely: when the Box API returns an item with a non-numeric `size` field,
    the parser's `int(item.get("size", 0))` raises ValueError. Pre-fix this would
    be silently swallowed and the user would see an empty result.
    """
    response = _FakeResponse(
        payload={
            "entries": [
                {
                    "id": "broken-item",
                    "name": "broken.pdf",
                    "type": "file",
                    "size": "not-a-number",  # forces int() to raise
                }
            ],
            "total_count": 1,
            "offset": 0,
            "limit": 10,
        }
    )
    with pytest.raises(ValueError, match="Box browse error"):
        _run_browse(monkeypatch, response=response)


def test_network_error_raises(monkeypatch: pytest.MonkeyPatch):
    """Pre-existing network-error propagation is preserved."""
    with pytest.raises(ValueError, match="Network error when accessing Box"):
        _run_browse(monkeypatch, response=requests.exceptions.ConnectionError("boom"))


# ---------------------------------------------------------------------------
# Source-level guard
# ---------------------------------------------------------------------------

def test_llm_catch_all_reraises_non_auth_errors():
    """Pin the dispatcher on box.py so a future refactor can't reintroduce the silent-empty return."""
    source = DEST_PY.read_text()
    # The bug shape: 'return OnlineDriveBrowseFilesResponse(result=[])' inside an
    # 'except Exception' block. (The pre-existing 'if not items: return empty'
    # path at the top of the try block is the legitimate 'folder is empty' signal
    # and is preserved, so it must still appear at the right indentation.)
    #
    # We assert two things: the catch-all no longer contains the silent return,
    # and a new 'raise ValueError(f"Box browse error: ...")' was added instead.
    assert 'raise ValueError(f"Box browse error: {str(e)}")' in source, (
        "the new non-auth re-raise is missing; the catch-all probably still returns empty"
    )
    # And the inner 'return OnlineDriveBrowseFilesResponse(result=[])' inside
    # the catch-all (which would be the bug pattern) is gone.
    #
    # We approximate: count the number of `result=[])` lines in the source and
    # verify the count is 1 (the legitimate 'empty folder' return), not 2
    # (the original buggy 'silent failure' return).
    silent_returns = source.count("return OnlineDriveBrowseFilesResponse(result=[])")
    assert silent_returns == 1, (
        f"expected exactly one legitimate 'return empty' (the empty-folder signal), "
        f"found {silent_returns}; if 2+, the catch-all still returns empty on errors"
    )


def test_llm_preserves_401_message():
    """Pin the auth guidance message so a future refactor doesn't drift away from the documented user-facing string."""
    source = DEST_PY.read_text()
    # The actual source string is slightly different (it includes the
    # '401 Unauthorized' parenthetical for clarity). The pin asserts the
    # user-facing guidance, not the exact bytes.
    assert "Authentication failed" in source
    assert "access token may have expired" in source
    assert "Please refresh or reauthorize" in source, (
        "the auth guidance string is missing; the issue body and the "
        "401-response tests both reference it"
    )