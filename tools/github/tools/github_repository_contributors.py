import json
from collections.abc import Generator
from typing import Any

import requests

from dify_plugin import Tool
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class GithubRepositoryContributorsTool(Tool):
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
            url = f"{api_domain}/repos/{owner}/{repo}/contributors"

            params = {"per_page": per_page}

            response = s.request(
                method="GET",
                headers=headers,
                url=url,
                params=params,
            )

            if response.status_code == 200:
                response_data = response.json()

                contributors = []
                for contributor in response_data:
                    contributor_info = {
                        "login": contributor.get("login", ""),
                        "id": contributor.get("id", 0),
                        "avatar_url": contributor.get("avatar_url", ""),
                        "url": contributor.get("html_url", ""),
                        "contributions": contributor.get("contributions", 0),
                        "type": contributor.get("type", ""),
                        "site_admin": contributor.get("site_admin", False),
                    }
                    contributors.append(contributor_info)

                s.close()

                if not contributors:
                    yield self.create_text_message(f"No contributors found in {owner}/{repo}")
                else:
                    yield self.create_text_message(
                        self.session.model.summary.invoke(
                            text=json.dumps(contributors, ensure_ascii=False),
                            instruction="Summarize the GitHub contributors in a structured format",
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
