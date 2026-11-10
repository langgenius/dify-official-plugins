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
            response = self.datasource._get_pages({})

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


if __name__ == "__main__":
    unittest.main()
