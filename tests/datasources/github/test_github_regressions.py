import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[3]


def load(path):
    spec = importlib.util.spec_from_file_location(path.replace("/", "_"), ROOT / path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def instance(cls):
    o = object.__new__(cls)
    o.runtime = NS(credentials={"access_token": "test"})
    return o


def test_github_readme_path():
    m = load("datasources/github/datasources/github.py")
    o = instance(m.GitHubDataSource)
    o.base_url = "https://api.github.com"

    def get(url, *a, **kw):
        if url.endswith("/user"):
            return {"id": 1, "login": "me"}
        if url.endswith("/readme"):
            return {
                "path": "docs/README.rst",
                "html_url": "https://example.test/readme",
            }
        return []

    o._make_request = Mock(side_effect=get)
    o._get_repositories = Mock(
        return_value=[
            {
                "full_name": "me/repo",
                "name": "repo",
                "html_url": "https://example.test/repo",
            }
        ]
    )
    pages = o._get_pages({}).result[0].pages
    assert any(p.page_id == "file:me/repo:docs/README.rst" for p in pages)
