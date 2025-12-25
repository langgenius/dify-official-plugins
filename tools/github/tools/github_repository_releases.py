import json
from collections.abc import Generator
from datetime import datetime
from typing import Any

import requests

from dify_plugin import Tool
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class GithubRepositoryReleasesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        owner = tool_parameters.get("owner", "")
        repo = tool_parameters.get("repo", "")
        per_page = tool_parameters.get("per_page", 10)

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
            url = f"{api_domain}/repos/{owner}/{repo}/releases"

            params = {"per_page": per_page}

            response = s.request(
                method="GET",
                headers=headers,
                url=url,
                params=params,
            )

            if response.status_code == 200:
                response_data = response.json()

                releases = []
                for release in response_data:
                    release_info = {
                        "id": release.get("id", 0),
                        "tag_name": release.get("tag_name", ""),
                        "name": release.get("name", ""),
                        "body": (release.get("body", "") or "")[:300] + "..."
                        if len(release.get("body", "") or "") > 300
                        else (release.get("body", "") or ""),
                        "url": release.get("html_url", ""),
                        "tarball_url": release.get("tarball_url", ""),
                        "zipball_url": release.get("zipball_url", ""),
                        "author": release.get("author", {}).get("login", ""),
                        "draft": release.get("draft", False),
                        "prerelease": release.get("prerelease", False),
                        "assets": [
                            {
                                "name": asset.get("name", ""),
                                "size": asset.get("size", 0),
                                "download_count": asset.get("download_count", 0),
                                "download_url": asset.get("browser_download_url", ""),
                            }
                            for asset in release.get("assets", [])
                        ],
                        "created_at": datetime.strptime(release.get("created_at", ""), "%Y-%m-%dT%H:%M:%SZ").strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if release.get("created_at")
                        else "",
                        "published_at": datetime.strptime(
                            release.get("published_at", ""), "%Y-%m-%dT%H:%M:%SZ"
                        ).strftime("%Y-%m-%d %H:%M:%S")
                        if release.get("published_at")
                        else "",
                    }
                    releases.append(release_info)

                s.close()

                if not releases:
                    yield self.create_text_message(f"No releases found in {owner}/{repo}")
                else:
                    yield self.create_text_message(
                        self.session.model.summary.invoke(
                            text=json.dumps(releases, ensure_ascii=False),
                            instruction="Summarize the GitHub releases in a structured format",
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
