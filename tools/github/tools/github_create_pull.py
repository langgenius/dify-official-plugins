import json
from collections.abc import Generator
from datetime import datetime
from typing import Any

import requests

from dify_plugin import Tool
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError

from .github_error_handler import handle_github_api_error


class GithubCreatePullTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a new pull request
        """
        owner = tool_parameters.get("owner", "")
        repo = tool_parameters.get("repo", "")
        title = tool_parameters.get("title", "")
        head = tool_parameters.get("head", "")
        base = tool_parameters.get("base", "")
        body = tool_parameters.get("body", "")
        draft = tool_parameters.get("draft", False)
        maintainer_can_modify = tool_parameters.get("maintainer_can_modify", True)
        credential_type = self.runtime.credential_type

        if not owner:
            yield self.create_text_message("Please input owner")
            return
        if not repo:
            yield self.create_text_message("Please input repo")
            return
        if not title:
            yield self.create_text_message("Please input title")
            return
        if not head:
            yield self.create_text_message("Please input head branch")
            return
        if not base:
            yield self.create_text_message("Please input base branch")
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
            url = f"{api_domain}/repos/{owner}/{repo}/pulls"

            payload = {
                "title": title,
                "head": head,
                "base": base,
                "draft": draft,
                "maintainer_can_modify": maintainer_can_modify,
            }
            if body:
                payload["body"] = body

            response = s.request(method="POST", headers=headers, url=url, json=payload)

            if response.status_code == 201:
                pull = response.json()

                result = {
                    "success": True,
                    "number": pull.get("number", 0),
                    "title": pull.get("title", ""),
                    "state": pull.get("state", ""),
                    "url": pull.get("html_url", ""),
                    "draft": pull.get("draft", False),
                    "head": {
                        "ref": pull.get("head", {}).get("ref", ""),
                        "sha": pull.get("head", {}).get("sha", "")[:7] if pull.get("head", {}).get("sha") else "",
                    },
                    "base": {
                        "ref": pull.get("base", {}).get("ref", ""),
                    },
                    "created_at": datetime.strptime(
                        pull.get("created_at", ""), "%Y-%m-%dT%H:%M:%SZ"
                    ).strftime("%Y-%m-%d %H:%M:%S") if pull.get("created_at") else "",
                }

                s.close()
                yield self.create_text_message(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                handle_github_api_error(response, f"create pull request in {owner}/{repo}")
        except InvokeError as e:
            yield self.create_text_message(f"❌ {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"❌ GitHub API request failed: {e}")
