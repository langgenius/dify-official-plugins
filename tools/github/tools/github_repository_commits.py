import json
from collections.abc import Generator
from datetime import datetime
from typing import Any

import requests

from dify_plugin import Tool
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class GithubRepositoryCommitsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        owner = tool_parameters.get("owner", "")
        repo = tool_parameters.get("repo", "")
        per_page = tool_parameters.get("per_page", 10)
        sha = tool_parameters.get("sha", "")
        path = tool_parameters.get("path", "")

        credential_type = self.runtime.credential_type

        if not owner:
            yield self.create_text_message("Please input owner")
            return
        if not repo:
            yield self.create_text_message("Please input repo")
            return

        if credential_type == CredentialType.API_KEY and "access_tokens" not in self.runtime.credentials:
            yield self.create_text_message("GitHub API Access Tokens is required.")
            return

        if credential_type == CredentialType.OAUTH and "access_tokens" not in self.runtime.credentials:
            yield self.create_text_message("GitHub OAuth Access Tokens is required.")
            return

        access_token = self.runtime.credentials.get("access_tokens")
        try:
            headers = {
                "Content-Type": "application/vnd.github+json",
                "Authorization": f"Bearer {access_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            s = requests.session()
            api_domain = "https://api.github.com"
            url = f"{api_domain}/repos/{owner}/{repo}/commits"

            params = {"per_page": per_page}

            if sha:
                params["sha"] = sha
            if path:
                params["path"] = path

            response = s.request(
                method="GET",
                headers=headers,
                url=url,
                params=params,
            )

            if response.status_code == 200:
                response_data = response.json()

                commits = []
                for commit in response_data:
                    commit_info = {
                        "sha": commit.get("sha", "")[:7],
                        "full_sha": commit.get("sha", ""),
                        "message": commit.get("commit", {}).get("message", ""),
                        "author": {
                            "name": commit.get("commit", {}).get("author", {}).get("name", ""),
                            "email": commit.get("commit", {}).get("author", {}).get("email", ""),
                            "date": datetime.strptime(
                                commit.get("commit", {}).get("author", {}).get("date", ""), "%Y-%m-%dT%H:%M:%SZ"
                            ).strftime("%Y-%m-%d %H:%M:%S")
                            if commit.get("commit", {}).get("author", {}).get("date")
                            else "",
                        },
                        "committer": {
                            "name": commit.get("commit", {}).get("committer", {}).get("name", ""),
                            "email": commit.get("commit", {}).get("committer", {}).get("email", ""),
                            "date": datetime.strptime(
                                commit.get("commit", {}).get("committer", {}).get("date", ""), "%Y-%m-%dT%H:%M:%SZ"
                            ).strftime("%Y-%m-%d %H:%M:%S")
                            if commit.get("commit", {}).get("committer", {}).get("date")
                            else "",
                        },
                        "url": commit.get("html_url", ""),
                        "comment_count": commit.get("commit", {}).get("comment_count", 0),
                        "verification": {
                            "verified": commit.get("commit", {}).get("verification", {}).get("verified", False),
                            "reason": commit.get("commit", {}).get("verification", {}).get("reason", ""),
                        },
                        "stats": {
                            "additions": commit.get("stats", {}).get("additions", 0),
                            "deletions": commit.get("stats", {}).get("deletions", 0),
                            "total": commit.get("stats", {}).get("total", 0),
                        }
                        if commit.get("stats")
                        else {},
                        "files_changed": len(commit.get("files", [])) if commit.get("files") else 0,
                    }
                    commits.append(commit_info)

                s.close()

                if not commits:
                    yield self.create_text_message(f"No commits found in {owner}/{repo}")
                else:
                    yield self.create_text_message(
                        self.session.model.summary.invoke(
                            text=json.dumps(commits, ensure_ascii=False),
                            instruction="Summarize the GitHub commits in a structured format",
                        )
                    )
            else:
                response_data = response.json()
                raise InvokeError(
                    f"Request failed: {response.status_code} {response_data.get('message', 'Unknown error')}"
                )
        except InvokeError as e:
            raise e
        except Exception as e:
            raise InvokeError(f"GitHub API request failed: {e}") from e
