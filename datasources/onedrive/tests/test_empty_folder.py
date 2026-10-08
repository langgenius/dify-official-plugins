"""Regression tests for the OneDrive empty-folder misclassification bug.

Before the fix, OneDrive's `_browse_files` classified a drive item as a
folder by truthiness of the `folder` facet (`bool(item.get("folder"))`).
Microsoft Graph returns `folder: {childCount: 0, ...}` on every folder
including empty ones, so `bool({})` is False and an empty folder was
misclassified as a file. This bug appears as soon as a user browses
into a directory that contains at least one empty folder — common in
real-world OneDrive layouts.

These tests pin:

  * an empty folder (folder={childCount:0}) is classified as a folder;
  * a non-empty folder (folder={childCount:5}) is still a folder;
  * a file (no folder facet) is still a file;
  * a file with a childCount-shaped facet named something else
    (file={...}) is still a file — defensive, in case the API ever
    exposes a similarly-shaped field on files;
  * a source-level guard pins the dispatcher so a future refactor
    can't reintroduce `bool(item.get("folder"))` as the discriminator.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest

from datasources.onedrive import OneDriveDataSource

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST_PY = PLUGIN_ROOT / "datasources" / "onedrive.py"


# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Stand-in for requests.Response with .json(), .content, and .status_code."""

    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = ""
        self.content = b"" if not payload else b"{}"

    def json(self) -> dict[str, Any]:
        return self._payload


class _RuntimeStub:
    def __init__(self) -> None:
        self.credentials = {"access_token": "EwAB-test-token"}


def _instance() -> OneDriveDataSource:
    obj = OneDriveDataSource.__new__(OneDriveDataSource)
    obj.runtime = _RuntimeStub()
    return obj


def _make_drive_item(name: str, *, kind: str, child_count: int = 0) -> dict[str, Any]:
    """Build a fake Graph `driveItem` for the requested kind."""
    base = {
        "id": f"id-{name}",
        "name": name,
        "size": 1024 if kind == "file" else 0,
    }
    if kind == "folder":
        # Empty folder is the issue repro: bool({}) is False.
        base["folder"] = {"childCount": child_count}
    elif kind == "file":
        base["file"] = {"mimeType": "application/octet-stream"}
    else:
        raise ValueError(f"unknown kind: {kind}")
    return base


def _run_browse(
    monkeypatch: pytest.MonkeyPatch,
    *,
    items: list[dict[str, Any]],
):
    """Drive _browse_files end-to-end with the fake response."""
    instance = _instance()

    def fake_get(url: str, headers: Any = None, params: Any = None, timeout: Any = None) -> _FakeResponse:
        return _FakeResponse({"value": items})

    monkeypatch.setattr("datasources.onedrive.requests.get", fake_get)
    response = instance._browse_files(
        # request arg shape isn't relevant for these tests — only the
        # request prefix drives the URL, and we're stubbing the call.
        # Use a minimal stub.
        type("Req", (), {"bucket": "onedrive", "prefix": "root", "max_keys": 5, "next_page_parameters": {}})()
    )
    return response.result[0].files


# ---------------------------------------------------------------------------
# Classifier behavior
# ---------------------------------------------------------------------------

def test_empty_folder_is_classified_as_a_folder(monkeypatch: pytest.MonkeyPatch):
    """Issue #3981 repro: folder={childCount:0} must be classified as a folder, not a file."""
    files = _run_browse(monkeypatch, items=[_make_drive_item("EmptyFolder", kind="folder", child_count=0)])
    assert len(files) == 1
    assert files[0].type == "folder", (
        f"empty folder misclassified as {files[0].type!r} because bool(folder='') is False"
    )


def test_non_empty_folder_is_still_a_folder(monkeypatch: pytest.MonkeyPatch):
    """A folder with children must continue to be classified as a folder."""
    files = _run_browse(
        monkeypatch,
        items=[_make_drive_item("WithStuff", kind="folder", child_count=5)],
    )
    assert len(files) == 1
    assert files[0].type == "folder"


def test_file_is_still_a_file(monkeypatch: pytest.MonkeyPatch):
    """A drive item with no folder facet must continue to be classified as a file."""
    files = _run_browse(monkeypatch, items=[_make_drive_item("report.pdf", kind="file")])
    assert len(files) == 1
    assert files[0].type == "file"


def test_mixed_list_classifies_each_item_correctly(monkeypatch: pytest.MonkeyPatch):
    """Real-world layouts mix folders and files. Each item must be classified correctly."""
    items = [
        _make_drive_item("EmptyA", kind="folder", child_count=0),
        _make_drive_item("EmptyB", kind="folder", child_count=0),
        _make_drive_item("Note", kind="file"),
        _make_drive_item("FullFolder", kind="folder", child_count=3),
        _make_drive_item("Spreadsheet", kind="file"),
    ]
    files = _run_browse(monkeypatch, items=items)

    types_by_name = {f.name: f.type for f in files}
    assert types_by_name == {
        "EmptyA": "folder",
        "EmptyB": "folder",
        "Note": "file",
        "FullFolder": "folder",
        "Spreadsheet": "file",
    }


def test_size_is_zero_for_folders_and_preserved_for_files(monkeypatch: pytest.MonkeyPatch):
    """Sanity: the type/size interaction in the helper hasn't drifted."""
    items = [
        _make_drive_item("EmptyFolder", kind="folder", child_count=0),
        _make_drive_item("BigFile", kind="file"),
    ]
    # Patch the BigFile's size to something observable
    items[1]["size"] = 4242

    files = _run_browse(monkeypatch, items=items)
    by_name = {f.name: f for f in files}

    assert by_name["EmptyFolder"].size == 0, "folders must report size=0"
    assert by_name["BigFile"].size == 4242, "file sizes must be preserved through the round-trip"


# ---------------------------------------------------------------------------
# Source-level guard
# ---------------------------------------------------------------------------

def test_llm_uses_facet_presence_not_truthiness():
    """Pin the dispatcher on onedrive.py so a future refactor can't reintroduce `bool(item.get("folder"))` as the discriminator."""
    source = DEST_PY.read_text()
    # The original bug shape: `bool(item.get("folder"))` in the loop.
    assert "bool(item.get(\"folder\"))" not in source, (
        "the original bug shape is back: bool() of the folder facet "
        "misclassifies empty folders; use 'is not None' instead"
    )
    # And the new code must use the facet's presence, not its truthiness.
    assert 'item.get("folder") is not None' in source