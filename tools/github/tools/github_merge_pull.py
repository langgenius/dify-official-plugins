import json
from collections.abc import Generator
from typing import Any

import requests

from dify_plugin import Tool
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError

from .github_error_handler import handle_github_api_error


class GithubMergePullTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Merge a pull request
        """
        owner = tool_parameters.get("owner", "")
        repo = tool_parameters.get("repo", "")
        pull_number = tool_parameters.get("pull_number")
        merge_method = tool_parameters.get("merge_method", "merge")
        commit_title = tool_parameters.get("commit_title", "")
        commit_message = tool_parameters.get("commit_message", "")
        sha = tool_parameters.get("sha", "")
        credential_type = self.runtime.credential_type

        if not owner:
            yield self.create_text_message("Please input owner")
            return
        if not repo:
            yield self.create_text_message("Please input repo")
            return
        if not pull_number:
            yield self.create_text_message("Please input pull_number")
            return

        # Validate merge method
        valid_methods = ["merge", "squash", "rebase"]
        if merge_method not in valid_methods:
            yield self.create_text_message(f"Invalid merge_method. Must be one of: {', '.join(valid_methods)}")
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
            url = f"{api_domain}/repos/{owner}/{repo}/pulls/{int(pull_number)}/merge"

            payload = {"merge_method": merge_method}
            if commit_title:
                payload["commit_title"] = commit_title
            if commit_message:
                payload["commit_message"] = commit_message
            if sha:
                payload["sha"] = sha

            response = s.request(method="PUT", headers=headers, url=url, json=payload)

            if response.status_code == 200:
                merge_data = response.json()

                result = {
                    "success": True,
                    "merged": merge_data.get("merged", False),
                    "message": merge_data.get("message", ""),
                    "sha": merge_data.get("sha", ""),
                }

                s.close()
                yield self.create_text_message(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                handle_github_api_error(response, f"merge pull request {owner}/{repo}#{pull_number}")
        except InvokeError as e:
            yield self.create_text_message(f"❌ {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"❌ GitHub API request failed: {e}")
