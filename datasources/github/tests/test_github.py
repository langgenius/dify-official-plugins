import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests

from datasources.github import GitHubDataSource, GitHubRepositoryBlockedError


class GitHubDataSourceTests(unittest.TestCase):
    def setUp(self):
        self.datasource = GitHubDataSource(
            runtime=SimpleNamespace(credentials={"access_token": "test-token"}),
            session=None,
        )

    @staticmethod
    def response(status, body, remaining=None, url="https://api.github.com/repos/FFXN/glados/readme"):
        response = requests.Response()
        response.status_code = status
        response.url = url
        response._content = json.dumps(body).encode()
        if remaining is not None:
            response.headers["X-RateLimit-Remaining"] = remaining
        return response

    def test_blocked_repository_403_is_not_treated_as_success(self):
        response = self.response(
            403,
            {"message": "Repository access blocked", "block": {"reason": "tos"}},
            remaining="100",
        )

        with self.assertRaisesRegex(GitHubRepositoryBlockedError, r"\(tos\).*FFXN/glados/readme"):
            self.datasource._handle_rate_limit(response)

    def test_other_403_is_an_error_and_rate_limit_is_preserved(self):
        denied = self.response(403, {"message": "Resource not accessible by personal access token"}, "100")
        with self.assertRaisesRegex(ValueError, "GitHub API error: 403"):
            self.datasource._handle_rate_limit(denied)

        limited = self.response(403, {"message": "API rate limit exceeded"}, "0")
        with self.assertRaisesRegex(ValueError, "GitHub API rate limit exceeded"):
            self.datasource._handle_rate_limit(limited)

    def test_page_list_skips_blocked_repository_and_keeps_other_repositories(self):
        repositories = [
            {"full_name": "FFXN/dify", "name": "dify", "html_url": "https://github.com/FFXN/dify"},
            {"full_name": "FFXN/glados", "name": "glados", "html_url": "https://github.com/FFXN/glados"},
            {"full_name": "FFXN/checkin", "name": "checkin", "html_url": "https://github.com/FFXN/checkin"},
        ]

        def get(url, **kwargs):
            if url.endswith("/user"):
                return self.response(200, {"login": "FFXN", "id": 1}, url=url)
            if url.endswith("/user/repos"):
                return self.response(200, repositories, url=url)
            if "/FFXN/glados/" in url:
                return self.response(
                    403,
                    {"message": "Repository access blocked", "block": {"reason": "tos"}},
                    remaining="100",
                    url=url,
                )
            if url.endswith("/FFXN/checkin/readme"):
                return self.response(404, {"message": "Not Found"}, url=url)
            if url.endswith("/readme"):
                return self.response(200, {"path": "docs/README.md", "html_url": url, "size": 42}, url=url)
            if url.endswith("/issues") or url.endswith("/pulls"):
                return self.response(200, [], url=url)
            raise AssertionError(f"Unexpected URL: {url}")

        with patch("datasources.github.requests.get", side_effect=get) as mocked_get:
            response = self.datasource._get_pages({"cursor": "10", "limit": 1})

        pages = response.result[0].pages
        self.assertEqual(
            [page.page_id for page in pages],
            ["repo:FFXN/dify", "file:FFXN/dify:docs/README.md", "repo:FFXN/checkin"],
        )
        self.assertEqual(response.result[0].total, 3)
        self.assertEqual(
            [call.args[0] for call in mocked_get.call_args_list if "/FFXN/glados/" in call.args[0]],
            ["https://api.github.com/repos/FFXN/glados/readme"],
        )

    def test_tree_root_paginates_repositories_without_loading_children(self):
        repositories = [
            {"full_name": "FFXN/dify", "name": "dify", "html_url": "https://github.com/FFXN/dify"},
            {"full_name": "FFXN/glados", "name": "glados", "html_url": "https://github.com/FFXN/glados"},
            {"full_name": "FFXN/checkin", "name": "checkin", "html_url": "https://github.com/FFXN/checkin"},
        ]

        def get(url, **kwargs):
            if url.endswith("/user"):
                return self.response(200, {"login": "FFXN", "id": 1}, url=url)
            if url.endswith("/user/repos"):
                return self.response(200, repositories, url=url)
            if url.endswith("/repos/FFXN/glados"):
                return self.response(
                    403,
                    {"message": "Repository access blocked", "block": {"reason": "tos"}},
                    remaining="100",
                    url=url,
                )
            if url.endswith(("/repos/FFXN/dify", "/repos/FFXN/checkin")):
                return self.response(200, {}, url=url)
            raise AssertionError(f"Tree root loaded a child: {url}")

        with patch("datasources.github.requests.get", side_effect=get) as mocked_get:
            first = self.datasource._get_pages({"view": "tree", "limit": 1})
            second = self.datasource._get_pages({"view": "tree", "limit": 1, "cursor": first.next_cursor})

        self.assertEqual(first.result[0].total, 2)
        self.assertEqual([page.page_id for page in first.result[0].pages], ["repo:FFXN/dify"])
        self.assertTrue(first.result[0].pages[0].has_children)
        self.assertEqual(first.next_cursor, "1")
        self.assertEqual(first.result[0].next_cursor, "1")
        self.assertEqual([page.page_id for page in second.result[0].pages], ["repo:FFXN/checkin"])
        self.assertIsNone(second.next_cursor)
        self.assertIsNone(second.result[0].next_cursor)
        self.assertEqual(first.model_dump()["next_cursor"], "1")
        self.assertEqual(first.model_dump()["result"][0]["next_cursor"], "1")
        self.assertTrue(first.model_dump()["result"][0]["pages"][0]["has_children"])
        self.assertFalse(any(call.args[0].endswith(("/readme", "/issues", "/pulls")) for call in mocked_get.call_args_list))

    def test_tree_child_lists_only_that_repository_and_keeps_page_ids(self):
        repositories = [
            {"full_name": "FFXN/dify", "name": "dify", "html_url": "https://github.com/FFXN/dify"},
            {"full_name": "FFXN/checkin", "name": "checkin", "html_url": "https://github.com/FFXN/checkin"},
        ]

        def get(url, **kwargs):
            if url.endswith("/user"):
                return self.response(200, {"login": "FFXN", "id": 1}, url=url)
            if url.endswith("/user/repos"):
                return self.response(200, repositories, url=url)
            if url.endswith("/FFXN/dify/readme"):
                return self.response(200, {"path": "README.md", "html_url": url, "size": 42}, url=url)
            if url.endswith("/FFXN/dify/issues"):
                return self.response(200, [
                    {"number": 1, "title": "Bug", "html_url": url, "state": "open", "user": {"login": "FFXN"}, "created_at": "2026-11-09"},
                    {"number": 2, "pull_request": {"url": url}},
                ], url=url)
            if url.endswith("/FFXN/dify/pulls"):
                return self.response(200, [
                    {"number": 2, "title": "Fix", "html_url": url, "state": "open", "user": {"login": "FFXN"}, "base": {"ref": "main"}, "head": {"ref": "fix"}},
                ], url=url)
            raise AssertionError(f"Unexpected repository request: {url}")

        with patch("datasources.github.requests.get", side_effect=get) as mocked_get:
            first = self.datasource._get_pages({"view": "tree", "parent_id": "repo:FFXN/dify", "limit": 2})
            second = self.datasource._get_pages({"view": "tree", "parent_id": "repo:FFXN/dify", "limit": 2, "cursor": "2"})

        self.assertEqual(first.result[0].total, 3)
        self.assertEqual([page.page_id for page in first.result[0].pages], ["file:FFXN/dify:README.md", "issue:FFXN/dify:1"])
        self.assertEqual(first.next_cursor, "2")
        self.assertEqual([page.page_id for page in second.result[0].pages], ["pr:FFXN/dify:2"])
        self.assertIsNone(second.next_cursor)
        self.assertTrue(all(page.parent_id == "repo:FFXN/dify" for page in first.result[0].pages + second.result[0].pages))
        self.assertFalse(any("/FFXN/checkin/" in call.args[0] for call in mocked_get.call_args_list))

    def test_tree_rejects_invalid_parent_and_pagination(self):
        with patch.object(self.datasource, "_make_request", return_value={"login": "FFXN", "id": 1}), \
             patch.object(self.datasource, "_get_repositories", return_value=[]):
            for parameters in (
                {"view": "tree", "parent_id": "issue:FFXN/dify:1"},
                {"view": "tree", "parent_id": "repo:FFXN/unknown"},
                {"view": "tree", "limit": 0},
                {"view": "tree", "cursor": "not-a-cursor"},
            ):
                with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                    self.datasource._get_pages(parameters)


if __name__ == "__main__":
    unittest.main()
