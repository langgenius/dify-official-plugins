import json
from collections.abc import Generator
from datetime import datetime
from typing import Any

import requests

from dify_plugin import Tool
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class GithubRepositoryInfoTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        owner = tool_parameters.get("owner", "")
        repo = tool_parameters.get("repo", "")
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
            url = f"{api_domain}/repos/{owner}/{repo}"

            response = s.request(
                method="GET",
                headers=headers,
                url=url,
            )

            if response.status_code == 200:
                response_data = response.json()

                # Extract key information
                repo_info = {
                    "name": response_data.get("name", ""),
                    "full_name": response_data.get("full_name", ""),
                    "description": response_data.get("description", ""),
                    "url": response_data.get("html_url", ""),
                    "clone_url": response_data.get("clone_url", ""),
                    "ssh_url": response_data.get("ssh_url", ""),
                    "language": response_data.get("language", ""),
                    "stars": response_data.get("stargazers_count", 0),
                    "forks": response_data.get("forks_count", 0),
                    "watchers": response_data.get("watchers_count", 0),
                    "open_issues": response_data.get("open_issues_count", 0),
                    "size": response_data.get("size", 0),
                    "default_branch": response_data.get("default_branch", ""),
                    "is_private": response_data.get("private", False),
                    "is_fork": response_data.get("fork", False),
                    "is_archived": response_data.get("archived", False),
                    "license": response_data.get("license", {}).get("name", "") if response_data.get("license") else "",
                    "created_at": datetime.strptime(response_data.get("created_at", ""), "%Y-%m-%dT%H:%M:%SZ").strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if response_data.get("created_at")
                    else "",
                    "updated_at": datetime.strptime(response_data.get("updated_at", ""), "%Y-%m-%dT%H:%M:%SZ").strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if response_data.get("updated_at")
                    else "",
                    "pushed_at": datetime.strptime(response_data.get("pushed_at", ""), "%Y-%m-%dT%H:%M:%SZ").strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if response_data.get("pushed_at")
                    else "",
                    "topics": response_data.get("topics", []),
                    "owner": {
                        "login": response_data.get("owner", {}).get("login", ""),
                        "type": response_data.get("owner", {}).get("type", ""),
                        "url": response_data.get("owner", {}).get("html_url", ""),
                    },
                }

                s.close()
                yield self.create_text_message(
                    self.session.model.summary.invoke(
                        text=json.dumps(repo_info, ensure_ascii=False),
                        instruction="Summarize the repository information in a structured format",
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
