import json
from collections.abc import Generator
from datetime import datetime
from typing import Any

import requests

from dify_plugin import Tool
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class GithubUserReposTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        username = tool_parameters.get("username", "")
        per_page = tool_parameters.get("per_page", 10)
        sort = tool_parameters.get("sort", "updated")
        direction = tool_parameters.get("direction", "desc")
        type = tool_parameters.get("type", "all")  # noqa: A001

        credential_type = self.runtime.credential_type

        if not username:
            yield self.create_text_message("Please input username")
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
            url = f"{api_domain}/users/{username}/repos"

            params = {"per_page": per_page, "sort": sort, "direction": direction, "type": type}

            response = s.request(
                method="GET",
                headers=headers,
                url=url,
                params=params,
            )

            if response.status_code == 200:
                response_data = response.json()

                repos = []
                for repo in response_data:
                    repo_info = {
                        "id": repo.get("id", 0),
                        "name": repo.get("name", ""),
                        "full_name": repo.get("full_name", ""),
                        "description": repo.get("description", ""),
                        "url": repo.get("html_url", ""),
                        "clone_url": repo.get("clone_url", ""),
                        "ssh_url": repo.get("ssh_url", ""),
                        "language": repo.get("language", ""),
                        "stars": repo.get("stargazers_count", 0),
                        "forks": repo.get("forks_count", 0),
                        "watchers": repo.get("watchers_count", 0),
                        "open_issues": repo.get("open_issues_count", 0),
                        "size": repo.get("size", 0),
                        "default_branch": repo.get("default_branch", ""),
                        "is_private": repo.get("private", False),
                        "is_fork": repo.get("fork", False),
                        "is_archived": repo.get("archived", False),
                        "license": repo.get("license", {}).get("name", "") if repo.get("license") else "",
                        "created_at": datetime.strptime(repo.get("created_at", ""), "%Y-%m-%dT%H:%M:%SZ").strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if repo.get("created_at")
                        else "",
                        "updated_at": datetime.strptime(repo.get("updated_at", ""), "%Y-%m-%dT%H:%M:%SZ").strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if repo.get("updated_at")
                        else "",
                        "pushed_at": datetime.strptime(repo.get("pushed_at", ""), "%Y-%m-%dT%H:%M:%SZ").strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if repo.get("pushed_at")
                        else "",
                        "topics": repo.get("topics", []),
                    }
                    repos.append(repo_info)

                s.close()

                if not repos:
                    yield self.create_text_message(f"No repositories found for user {username}")
                else:
                    yield self.create_text_message(
                        self.session.model.summary.invoke(
                            text=json.dumps(repos, ensure_ascii=False),
                            instruction="Summarize the GitHub user repositories in a structured format",
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
