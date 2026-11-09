import base64
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
    def response(status, body, remaining=None, url="https://api.github.com/repos/FFXN/glados/readme", link=None):
        response = requests.Response()
        response.status_code = status
        response.url = url
        response._content = json.dumps(body).encode()
        if remaining is not None:
            response.headers["X-RateLimit-Remaining"] = remaining
        if link is not None:
            response.headers["Link"] = link
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

    def test_tree_repository_exposes_lazy_contents_issues_and_pr_groups(self):
        repositories = [
            {"full_name": "FFXN/dify", "name": "dify", "html_url": "https://github.com/FFXN/dify"},
            {"full_name": "FFXN/checkin", "name": "checkin", "html_url": "https://github.com/FFXN/checkin"},
        ]

        def get(url, **kwargs):
            if url.endswith("/user"):
                return self.response(200, {"login": "FFXN", "id": 1}, url=url)
            if url.endswith("/user/repos"):
                return self.response(200, repositories, url=url)
            if url.endswith("/repos/FFXN/dify"):
                return self.response(200, {}, url=url)
            raise AssertionError(f"Unexpected repository request: {url}")

        with patch("datasources.github.requests.get", side_effect=get) as mocked_get:
            response = self.datasource._get_pages({"view": "tree", "parent_id": "repo:FFXN/dify", "limit": 30})

        self.assertEqual(response.result[0].total, 3)
        self.assertEqual(
            [page.page_id for page in response.result[0].pages],
            ["contents:FFXN/dify", "issues:FFXN/dify", "prs:FFXN/dify"],
        )
        self.assertTrue(all(page.has_children and page.parent_id == "repo:FFXN/dify" for page in response.result[0].pages))
        self.assertIsNone(response.next_cursor)
        self.assertFalse(any(call.args[0].endswith(("/contents", "/issues", "/pulls")) for call in mocked_get.call_args_list))

    def test_tree_issue_and_pr_groups_paginate_independently(self):
        repositories = [{"full_name": "FFXN/dify", "name": "dify"}]

        def get(url, **kwargs):
            if url.endswith("/user"):
                return self.response(200, {"login": "FFXN", "id": 1}, url=url)
            if url.endswith("/user/repos"):
                return self.response(200, repositories, url=url)
            if url.endswith("/repos/FFXN/dify"):
                return self.response(200, {}, url=url)
            page = kwargs.get("params", {}).get("page")
            if url.endswith("/issues"):
                body = ([
                    {"number": 1, "title": "Bug"},
                    {"number": 2, "pull_request": {"url": url}},
                ] if page == 1 else [{"number": 3, "title": "Another bug"}])
                link = f'<{url}?page=2>; rel="next"' if page == 1 else None
                return self.response(200, body, url=url, link=link)
            if url.endswith("/pulls"):
                body = [{"number": 10 if page == 1 else 11, "title": "Fix"}]
                link = f'<{url}?page=2>; rel="next"' if page == 1 else None
                return self.response(200, body, url=url, link=link)
            raise AssertionError(f"Unexpected URL: {url}")

        with patch("datasources.github.requests.get", side_effect=get) as mocked_get:
            issues_first = self.datasource._get_pages({"view": "tree", "parent_id": "issues:FFXN/dify", "limit": 30})
            issues_second = self.datasource._get_pages({"view": "tree", "parent_id": "issues:FFXN/dify", "limit": 30, "cursor": "2"})
            prs_first = self.datasource._get_pages({"view": "tree", "parent_id": "prs:FFXN/dify", "limit": 30})
            prs_second = self.datasource._get_pages({"view": "tree", "parent_id": "prs:FFXN/dify", "limit": 30, "cursor": "2"})

        self.assertEqual([page.page_id for page in issues_first.result[0].pages], ["issue:FFXN/dify:1"])
        self.assertEqual(issues_first.result[0].next_cursor, "2")
        self.assertEqual([page.page_id for page in issues_second.result[0].pages], ["issue:FFXN/dify:3"])
        self.assertIsNone(issues_second.next_cursor)
        self.assertEqual([page.page_id for page in prs_first.result[0].pages], ["pr:FFXN/dify:10"])
        self.assertEqual(prs_first.result[0].next_cursor, "2")
        self.assertEqual([page.page_id for page in prs_second.result[0].pages], ["pr:FFXN/dify:11"])
        self.assertTrue(all(page.parent_id == "prs:FFXN/dify" for page in prs_first.result[0].pages))
        discussion_calls = [call for call in mocked_get.call_args_list if call.args[0].endswith(("/issues", "/pulls"))]
        self.assertEqual([call.kwargs["params"]["page"] for call in discussion_calls], [1, 2, 1, 2])

    def test_tree_contents_browses_nested_directories_and_paginates_files(self):
        repositories = [{"full_name": "FFXN/dify", "name": "dify"}]

        def get(url, **kwargs):
            if url.endswith("/user"):
                return self.response(200, {"login": "FFXN", "id": 1}, url=url)
            if url.endswith("/user/repos"):
                return self.response(200, repositories, url=url)
            if url.endswith("/repos/FFXN/dify"):
                return self.response(200, {}, url=url)
            if url.endswith("/contents"):
                return self.response(200, [
                    {"type": "dir", "path": "src", "name": "src", "sha": "dir-sha"},
                    {"type": "file", "path": "README.md", "name": "README.md", "sha": "readme-sha"},
                ], url=url)
            if url.endswith("/contents/src"):
                return self.response(200, [
                    {"type": "file", "path": "src/main.py", "name": "main.py", "sha": "file-sha"},
                ], url=url)
            raise AssertionError(f"Unexpected URL: {url}")

        with patch("datasources.github.requests.get", side_effect=get):
            root = self.datasource._get_pages({"view": "tree", "parent_id": "contents:FFXN/dify", "limit": 1})
            next_page = self.datasource._get_pages({"view": "tree", "parent_id": "contents:FFXN/dify", "limit": 1, "cursor": "1"})
            nested = self.datasource._get_pages({"view": "tree", "parent_id": "dir:FFXN/dify:src", "limit": 30})

        self.assertEqual(root.result[0].pages[0].page_id, "dir:FFXN/dify:src")
        self.assertTrue(root.result[0].pages[0].has_children)
        self.assertEqual(root.next_cursor, "1")
        self.assertEqual(next_page.result[0].pages[0].page_id, "file:FFXN/dify:README.md")
        self.assertEqual(next_page.result[0].pages[0].parent_id, "contents:FFXN/dify")
        self.assertEqual(nested.result[0].pages[0].page_id, "file:FFXN/dify:src/main.py")
        self.assertEqual(nested.result[0].pages[0].parent_id, "dir:FFXN/dify:src")
        self.assertIsNone(nested.next_cursor)

    def test_code_file_content_uses_encoded_github_path(self):
        page_id = "file:FFXN/dify:src/a #b.py"
        encoded_url = "https://api.github.com/repos/FFXN/dify/contents/src/a%20%23b.py"

        def get(url, **kwargs):
            self.assertEqual(url, encoded_url)
            return self.response(200, {
                "type": "file",
                "name": "a #b.py",
                "encoding": "base64",
                "content": base64.b64encode(b"print('ok')").decode(),
            }, url=url)

        with patch("datasources.github.requests.get", side_effect=get):
            messages = list(self.datasource._get_content(SimpleNamespace(page_id=page_id)))

        self.assertTrue(messages)

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
