"""Regression tests for the README path bug fixed in this PR.

Before the fix, ``_get_pages`` and ``_get_project_content`` hardcoded
``"README.md"`` against the GitLab API in the file lookup URL, the page id,
the README web URL, and ``metadata.file_path``. Repos whose default README
lives in a subdirectory (``docs/README.rst``) or uses a non-``md`` extension
(``README.markdown``) silently got a 404 from the GitLab content API and
the page opened to an empty README.

The fix adds ``_get_default_readme_path(project_id)`` which queries the
project tree and returns the first README-like entry. It then threads the
resolved path through both call sites and uses ``urllib.parse.quote`` for
URL encoding instead of a naive ``replace('/', '%2F')``.

Tests pin:

  * ``_get_default_readme_path`` returns the API-resolved path
    (case- and extension-aware, preferring common extensions);
  * the listing page emits ``page_id`` with the actual README path, not a
    hardcoded literal;
  * a project with no README falls back silently (no crash, no entry);
  * a project whose README is in a subdirectory resolves correctly;
  * ``_get_file_content`` URL-decodes the path segment for legacy and new
    page ids and matches the GitLab-API path the listing used;
  * source-level guards pin the file so a future refactor can't reintroduce
    the hardcoded ``"README.md"`` literal in the page_id template.
"""

from __future__ import annotations

import pathlib
import types
from typing import Any

import pytest

from datasources.gitlab import GitLabDataSource

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[1]
GITLAB_PY = PLUGIN_ROOT / "datasources" / "gitlab.py"


def _install_response_type_stub(obj: GitLabDataSource) -> None:
    """Attach a ``response_type`` stub so ``create_variable_message(...)`` works.

    ``create_variable_message`` constructs a Pydantic message via
    ``self.response_type(type=..., message=...)``. Building a real Pydantic
    message would require the dify_plugin runtime to be fully initialized;
    a SimpleNamespace stub satisfies the call site and lets the tests
    inspect the captured arguments.
    """
    captured: list[dict[str, Any]] = []

    def _stub(**kwargs: Any) -> Any:
        captured.append(kwargs)
        return types.SimpleNamespace(**kwargs)

    obj.response_type = _stub  # type: ignore[assignment]
    obj._response_type_captured = captured  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------


class _RuntimeStub:
    """Stub for ``self.runtime.credentials`` that ``_get_headers`` reads."""

    def __init__(self) -> None:
        self.credentials = {"access_token": "glpat-test"}


def _instance() -> GitLabDataSource:
    """Build a bare instance without invoking the dify_plugin ``__init__``."""
    obj = GitLabDataSource.__new__(GitLabDataSource)
    obj.runtime = _RuntimeStub()
    obj.gitlab_url = "https://gitlab.com"
    obj.base_url = "https://gitlab.com/api/v4"
    return obj


def _make_user(login: str = "octocat") -> dict[str, Any]:
    return {"login": login, "name": login, "id": 1, "avatar_url": "https://example.com/a.png"}


def _make_repo(
    path_with_namespace: str = "group/hello-world",
    project_id: int = 42,
    updated_at: str = "2026-09-01T00:00:00Z",
    default_branch: str = "main",
) -> dict[str, Any]:
    return {
        "id": project_id,
        "name": path_with_namespace.rsplit("/", 1)[-1],
        "path_with_namespace": path_with_namespace,
        "web_url": f"https://gitlab.com/{path_with_namespace}",
        "description": "test repo",
        "default_branch": default_branch,
        "star_count": 0,
        "last_activity_at": updated_at,
        "visibility": "public",
    }


def _make_readme_file(path: str, size: int = 1024) -> dict[str, Any]:
    return {
        "path": path,
        "name": path.rsplit("/", 1)[-1],
        "encoding": "base64",
        "content": "VGVzdA==",  # base64("Test")
        "size": size,
    }


def _make_tree_entry(path: str, kind: str = "blob") -> dict[str, Any]:
    return {
        "path": path,
        "type": kind,
        "id": f"abc-{path}",
        "name": path.rsplit("/", 1)[-1],
    }


def _stub_make_request(
    obj: GitLabDataSource,
    *,
    user: dict[str, Any] | None = None,
    projects: list[dict[str, Any]] | None = None,
    tree: Any | None = None,
    readme_file: dict[str, Any] | None = None,
) -> tuple[Any, list[str]]:
    """Build a ``_make_request`` stub that routes the URLs ``_get_pages`` issues.

    Returns ``ValueError`` for any URL it doesn't recognize so the
    caller's ``except ValueError`` blocks swallow the error.
    """
    captured: list[str] = []

    def _fake(url: str, params: dict[str, Any] | None = None) -> Any:
        captured.append(url)
        if user is not None and url.endswith("/user"):
            return user
        if projects is not None and url.endswith(
            f"{obj.base_url}/projects?membership=true&simple=true&per_page=20&order_by=last_activity_at&page=1"
        ):
            return projects
        if tree is not None and (
            url.endswith("/repository/tree") or "/repository/tree?" in url
        ):
            return tree
        if readme_file is not None and "/repository/files/" in url:
            return readme_file
        if url.endswith("/issues"):
            return []
        if url.endswith("/merge_requests"):
            return []
        raise ValueError(f"_get_pages hit an unstubbed URL: {url}")

    return _fake, captured


# ---------------------------------------------------------------------------
# _get_default_readme_path unit cases
# ---------------------------------------------------------------------------


def test_get_default_readme_path_returns_default_for_root_readme_md() -> None:
    """The trivial case: ``README.md`` at the repo root resolves to ``README.md``."""
    obj = _instance()
    obj._make_request = lambda url, params=None: [
        _make_tree_entry("README.md"),
        _make_tree_entry("src/main.py"),
    ]
    assert obj._get_default_readme_path(42) == "README.md"


@pytest.mark.parametrize(
    "tree_entries, expected",
    [
        ([_make_tree_entry("README.markdown")], "README.markdown"),
        ([_make_tree_entry("README.rst")], "README.rst"),
        ([_make_tree_entry("readme.md")], "readme.md"),  # case-insensitive
        ([_make_tree_entry("README.txt")], "README.txt"),
    ],
)
def test_get_default_readme_path_extension_variants(
    tree_entries: list[dict[str, Any]],
    expected: str,
) -> None:
    obj = _instance()
    obj._make_request = lambda url, params=None: tree_entries  # type: ignore[assignment]
    assert obj._get_default_readme_path(42) == expected


def test_get_default_readme_path_prefers_md_over_rst() -> None:
    """When several README-like entries coexist, ``.md`` wins over ``.rst``."""
    obj = _instance()
    tree = [
        _make_tree_entry("README.rst"),
        _make_tree_entry("README.markdown"),
        _make_tree_entry("README.md"),
    ]
    obj._make_request = lambda url, params=None: tree  # type: ignore[assignment]
    assert obj._get_default_readme_path(42) == "README.md"


def test_get_default_readme_path_subdirectory_no_root() -> None:
    """The key bug case: README living in a subdirectory resolves to the subtree path."""
    obj = _instance()
    tree = [
        _make_tree_entry("src/main.py"),
        _make_tree_entry("docs/README.rst"),
    ]
    obj._make_request = lambda url, params=None: tree  # type: ignore[assignment]
    assert obj._get_default_readme_path(42) == "docs/README.rst"


def test_get_default_readme_path_returns_none_when_tree_empty() -> None:
    obj = _instance()
    obj._make_request = lambda url, params=None: []
    assert obj._get_default_readme_path(42) is None


def test_get_default_readme_path_returns_none_on_tree_query_error() -> None:
    """A failing tree query should not crash; the caller's fallback path runs."""
    obj = _instance()

    def _boom(url: str, params: dict[str, Any] | None = None) -> Any:
        raise ValueError("tree query failed")

    obj._make_request = _boom  # type: ignore[assignment]
    assert obj._get_default_readme_path(42) is None


def test_get_default_readme_path_returns_none_when_response_is_not_list() -> None:
    """A defensive guard against an unexpected tree response shape."""
    obj = _instance()
    obj._make_request = lambda url, params=None: {"unrelated": "object"}
    assert obj._get_default_readme_path(42) is None


def test_get_default_readme_path_skips_tree_subtrees() -> None:
    """Subtrees (directory entries) must not be mistaken for README files."""
    obj = _instance()
    tree = [
        {"path": "readme", "type": "tree", "name": "readme"},  # a directory named "readme"
        _make_tree_entry("README.md"),
    ]
    obj._make_request = lambda url, params=None: tree  # type: ignore[assignment]
    assert obj._get_default_readme_path(42) == "README.md"


# ---------------------------------------------------------------------------
# _get_pages integration
# ---------------------------------------------------------------------------


def test_get_pages_emits_readme_entry_with_resolved_path_in_subdir() -> None:
    """The full listing flow must thread the resolved README path through ``page_id``."""
    obj = _instance()
    fake_request, captured = _stub_make_request(
        obj,
        user=_make_user(),
        tree=[_make_tree_entry("docs/README.rst")],
        readme_file=_make_readme_file("docs/README.rst", size=512),
    )
    obj._make_request = fake_request  # type: ignore[assignment]
    obj._get_projects = lambda max_projects=20: [_make_repo()]  # type: ignore[assignment]

    response = obj._get_pages({})
    info = response.result[0]
    readme_pages = [p for p in info.pages if p.page_name.endswith("- README")]
    assert len(readme_pages) == 1, "expected exactly one README page entry"
    readme = readme_pages[0]

    assert "docs/README.rst" in readme.page_id
    assert "README.md" not in readme.page_id.split(":")[-1]  # the path segment is not the literal "README.md"
    # The URL the API call hits must percent-encode the slash.
    assert any("/repository/files/docs%2FREADME.rst" in u for u in captured), (
        f"expected URL-encoded subdir path; got captured URLs {captured}"
    )


def test_get_pages_skips_readme_when_project_has_none() -> None:
    """A project without a README must not emit a README page entry."""
    obj = _instance()
    fake_request, _ = _stub_make_request(
        obj,
        user=_make_user(),
        tree=[_make_tree_entry("src/main.py"), _make_tree_entry("pyproject.toml")],
    )
    obj._make_request = fake_request  # type: ignore[assignment]
    obj._get_projects = lambda max_projects=20: [_make_repo()]  # type: ignore[assignment]

    response = obj._get_pages({})
    info = response.result[0]
    readme_pages = [p for p in info.pages if p.page_name.endswith("- README")]
    assert readme_pages == []


@pytest.mark.parametrize("tree_path", ["README.rst", "README.markdown", "README.txt"])
def test_get_pages_emits_readme_entry_for_non_md_extension(tree_path: str) -> None:
    """README.rst and README.markdown resolve and surface in the listing."""
    obj = _instance()
    fake_request, _ = _stub_make_request(
        obj,
        user=_make_user(),
        tree=[_make_tree_entry(tree_path)],
        readme_file=_make_readme_file(tree_path),
    )
    obj._make_request = fake_request  # type: ignore[assignment]
    obj._get_projects = lambda max_projects=20: [_make_repo()]  # type: ignore[assignment]

    response = obj._get_pages({})
    info = response.result[0]
    readme_pages = [p for p in info.pages if p.page_name.endswith("- README")]
    assert len(readme_pages) == 1, f"expected a README entry for {tree_path}"
    assert tree_path in readme_pages[0].page_id


# ---------------------------------------------------------------------------
# _get_file_content backward compat + URL encoding
# ---------------------------------------------------------------------------


def test_get_file_content_url_encodes_subdir_path() -> None:
    """The page_id emitted by the listing must roundtrip cleanly through ``_get_file_content`` for a subdirectory README."""
    obj = _instance()
    _install_response_type_stub(obj)
    captured: list[str] = []

    def _fake_request(url: str, params: dict[str, Any] | None = None) -> Any:
        captured.append(url)
        if "/repository/files/" in url:
            return _make_readme_file("docs/README.rst")
        raise ValueError(f"unexpected URL {url}")

    obj._make_request = _fake_request  # type: ignore[assignment]

    page_id = "file:group/hello-world:docs/README.rst"
    # Drain the generator so the side effect (network call) runs.
    list(obj._get_file_content(page_id))
    assert any("/repository/files/docs%2FREADME.rst" in u for u in captured), (
        f"expected URL-encoded subdir path; got {captured}"
    )


def test_get_file_content_accepts_legacy_readme_md_page_id() -> None:
    """Legacy bookmarked page_id values like ``file:ns:README.md`` must still resolve."""
    obj = _instance()
    _install_response_type_stub(obj)
    captured: list[str] = []

    def _fake_request(url: str, params: dict[str, Any] | None = None) -> Any:
        captured.append(url)
        if "/repository/files/" in url:
            return _make_readme_file("README.md")
        raise ValueError(f"unexpected URL {url}")

    obj._make_request = _fake_request  # type: ignore[assignment]

    list(obj._get_file_content("file:group/hello-world:README.md"))
    assert any("/repository/files/README.md" in u for u in captured)


# ---------------------------------------------------------------------------
# Source-level guards
# ---------------------------------------------------------------------------


def test_get_pages_does_not_hardcode_readme_md_in_page_id() -> None:
    """Pin the listing flow so a future refactor can't reintroduce the hardcoded literal."""
    source = GITLAB_PY.read_text(encoding="utf-8")

    # Carve out only the ``_get_pages`` body so the page_id/metadata/url
    # assertions are specific to that function and don't accidentally
    # pass on a literal "README.md" substring in another part of the
    # module.
    start = source.find("def _get_pages(")
    assert start != -1, "_get_pages not found in source"
    end = source.find("\n    def ", start + 1)
    snippet = source[start:end]

    # The page_id template should reference the resolved ``readme_path``.
    assert "f\"file:{project['path_with_namespace']}:{readme_path}\"" in snippet, (
        "expected page_id to source from the resolved readme_path placeholder"
    )
    assert "f\"file:{project['path_with_namespace']}:README.md\"" not in snippet, (
        "page_id must not hardcode the README.md literal"
    )
    # metadata.file_path should reference the resolved path.
    assert "\"file_path\": readme_path" in snippet, (
        "metadata.file_path should source from the resolved readme_path"
    )
    assert "\"file_path\": \"README.md\"" not in snippet, (
        "metadata.file_path must not hardcode the README.md literal"
    )


def test_get_project_content_does_not_hardcode_readme_md_in_request() -> None:
    """Pin ``_get_project_content`` so a future refactor can't reintroduce the hardcoded literal in the API URL."""
    source = GITLAB_PY.read_text(encoding="utf-8")
    start = source.find("def _get_project_content(")
    assert start != -1, "_get_project_content not found in source"
    end = source.find("\n    def ", start + 1)
    snippet = source[start:end]

    assert "readme_path" in snippet, (
        "_get_project_content should consult _get_default_readme_path"
    )
    assert "/repository/files/README.md" not in snippet, (
        "_get_project_content must not hardcode README.md in the file lookup URL"
    )
