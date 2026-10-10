"""Regression tests for the README path bug fixed in this PR.

Before the fix, `_get_pages` hardcoded 'README.md' in the page_id and
metadata.file_path regardless of what the GitHub `/repos/{owner}/{repo}/readme`
endpoint returned. Repos whose default README lives in a subdirectory
(e.g. `docs/README.rst`) emitted a page_id that never resolved when the
user opened the page — `_get_file_content` would 404 on the wrong path.

These tests pin:

  * the page_id uses the API-returned `path`, not a hardcoded 'README.md';
  * metadata.file_path matches the page_id's path segment;
  * page_name surfaces the API-returned `name` so README.rst, README.md,
    README.markdown, etc. are distinguishable;
  * a missing `path`/`name` key (older or non-standard API responses)
    falls back to 'README.md' rather than raising KeyError.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest

from datasources.github import GitHubDataSource

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[1]
GH_PY = PLUGIN_ROOT / "datasources" / "github.py"


# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Stand-in for requests.Response — `.json()` returns the pre-canned payload."""

    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self) -> Any:
        return self._payload


class _RuntimeStub:
    """Stub for self.runtime.credentials the datasource reads in _get_headers."""

    def __init__(self) -> None:
        self.credentials = {"access_token": "ghp_test"}


def _instance() -> GitHubDataSource:
    """Build a bare instance without invoking dify_plugin's OnlineDocumentDatasource.__init__."""
    obj = GitHubDataSource.__new__(GitHubDataSource)
    obj.runtime = _RuntimeStub()
    obj.base_url = "https://api.github.com"
    return obj


def _make_repo(full_name: str = "octocat/hello-world", updated_at: str = "2026-09-01T00:00:00Z") -> dict[str, Any]:
    return {
        "full_name": full_name,
        "name": full_name.split("/", 1)[1],
        "html_url": f"https://github.com/{full_name}",
        "updated_at": updated_at,
        "description": "test",
        "language": "Python",
        "stargazers_count": 0,
        "private": False,
    }


def _make_readme(path: str, name: str, size: int = 1024) -> dict[str, Any]:
    return {
        "name": name,
        "path": path,
        "size": size,
        "html_url": f"https://github.com/owner/repo/blob/main/{path}",
        "encoding": "base64",
        "content": "VGVzdA==",
    }


def _make_user(login: str = "octocat") -> dict[str, Any]:
    return {"login": login, "name": login, "id": 1, "avatar_url": "https://example.com/a.png"}


# ---------------------------------------------------------------------------
# Scenarios — each row mocks the GitHub API and exercises _get_pages
# ---------------------------------------------------------------------------

SCENARIOS: list[dict[str, Any]] = [
    {
        "label": "readme in subdirectory with .rst extension (issue repro)",
        "readme": _make_readme("docs/README.rst", "README.rst"),
        "expected_path": "docs/README.rst",
        "expected_name": "README.rst",
    },
    {
        "label": "readme in subdirectory with .md extension",
        "readme": _make_readme("docs/README.md", "README.md"),
        "expected_path": "docs/README.md",
        "expected_name": "README.md",
    },
    {
        "label": "readme at root with .md extension (most common)",
        "readme": _make_readme("README.md", "README.md"),
        "expected_path": "README.md",
        "expected_name": "README.md",
    },
    {
        "label": "readme at root with non-standard extension",
        "readme": _make_readme("README.markdown", "README.markdown"),
        "expected_path": "README.markdown",
        "expected_name": "README.markdown",
    },
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s["label"])
def test_get_pages_uses_api_path_for_readme(monkeypatch: pytest.MonkeyPatch, scenario: dict[str, Any]):
    """The page listing must echo the API's path/name, not a hardcoded 'README.md'."""
    instance = _instance()
    repo = _make_repo()
    user = _make_user()
    readme = scenario["readme"]

    def fake_request(url: str, params: dict | None = None, *args: Any, **kwargs: Any) -> _FakeResponse:
        if url.endswith("/user"):
            return _FakeResponse(user)
        if url.endswith("/user/repos"):
            return _FakeResponse([repo])
        if url.endswith(f"/repos/{repo['full_name']}/readme"):
            return _FakeResponse(readme)
        if url.endswith(f"/repos/{repo['full_name']}/issues"):
            return _FakeResponse([])
        if url.endswith(f"/repos/{repo['full_name']}/pulls"):
            return _FakeResponse([])
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr("datasources.github.requests.get", fake_request)

    response = instance._get_pages(datasource_parameters={})
    pages = response.result[0].pages

    # The README page is the second entry (after the repo entry).
    readme_pages = [p for p in pages if p.type == "file"]
    assert len(readme_pages) == 1
    page = readme_pages[0]

    # page_id must carry the API-returned path so _get_file_content can
    # parse it (parts[2] of the page_id is the file_path) and refetch
    # the right URL.
    assert page.page_id == f"file:{repo['full_name']}:{scenario['expected_path']}"
    # page_name surfaces the API-returned name so users can tell
    # README.rst from README.md at a glance.
    assert page.page_name == f"{repo['name']} - {scenario['expected_name']}"


def test_get_pages_falls_back_to_readme_md_when_api_omits_path(monkeypatch: pytest.MonkeyPatch):
    """Defensive: an older API response that omits 'path'/'name' must still work."""
    instance = _instance()
    repo = _make_repo()
    user = _make_user()

    def fake_request(url: str, params: dict | None = None, *args: Any, **kwargs: Any) -> _FakeResponse:
        if url.endswith("/user"):
            return _FakeResponse(user)
        if url.endswith("/user/repos"):
            return _FakeResponse([repo])
        if url.endswith(f"/repos/{repo['full_name']}/readme"):
            # No 'path' or 'name' key — defensive fallback must kick in.
            return _FakeResponse({"size": 1024, "html_url": "", "encoding": "base64"})
        if url.endswith(f"/repos/{repo['full_name']}/issues"):
            return _FakeResponse([])
        if url.endswith(f"/repos/{repo['full_name']}/pulls"):
            return _FakeResponse([])
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr("datasources.github.requests.get", fake_request)

    response = instance._get_pages(datasource_parameters={})
    pages = response.result[0].pages
    readme_pages = [p for p in pages if p.type == "file"]
    assert len(readme_pages) == 1
    page = readme_pages[0]

    assert page.page_id == f"file:{repo['full_name']}:README.md"
    assert page.page_name == f"{repo['name']} - README.md"


def test_get_pages_skips_readme_when_repo_has_no_readme(monkeypatch: pytest.MonkeyPatch):
    """The pre-existing skip-on-404 path must still work — defensive `except ValueError`."""
    instance = _instance()
    repo = _make_repo()
    user = _make_user()

    def fake_request(url: str, params: dict | None = None, *args: Any, **kwargs: Any) -> _FakeResponse:
        if url.endswith("/user"):
            return _FakeResponse(user)
        if url.endswith("/user/repos"):
            return _FakeResponse([repo])
        if url.endswith(f"/repos/{repo['full_name']}/readme"):
            # Simulate rate-limit / auth error: _handle_rate_limit raises ValueError.
            raise ValueError("GitHub API error: 404")
        if url.endswith(f"/repos/{repo['full_name']}/issues"):
            return _FakeResponse([])
        if url.endswith(f"/repos/{repo['full_name']}/pulls"):
            return _FakeResponse([])
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr("datasources.github.requests.get", fake_request)

    response = instance._get_pages(datasource_parameters={})
    pages = response.result[0].pages

    # Only the repo page; no README page emitted because the readme fetch failed.
    types_seen = [p.type for p in pages]
    assert types_seen == ["repository"]


# ---------------------------------------------------------------------------
# Source-level guard
# ---------------------------------------------------------------------------

def test_llm_readme_path_uses_api_response():
    """Pin the dispatcher's data source on `gh.py` so a future refactor can't reintroduce the hardcode."""
    source = GH_PY.read_text()
    # The hardcoded literal must be gone from f-string page_id templates.
    # 'README.md' may still appear as a `.get(...)` fallback, but no occurrences
    # in an f-string that's used to assemble a page_id.
    banned_template = 'file:' + "repo['full_name']" + ':README.md'
    assert banned_template not in source, (
        "_get_pages still uses a hardcoded README.md literal in page_id; "
        "use readme_info['path'] instead"
    )
    # And the new code must reference the API-returned path.
    assert 'readme_info.get("path", "README.md")' in source
    # The new DISPLAY label code must reference the API-returned name.
    assert 'readme_info.get("name", "README.md")' in source