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


class GithubIssueCommentTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a comment on an issue
        """
        owner = tool_parameters.get("owner", "")
        repo = tool_parameters.get("repo", "")
        issue_number = tool_parameters.get("issue_number")
        body = tool_parameters.get("body", "")
        credential_type = self.runtime.credential_type

        if not owner:
            yield self.create_text_message("Please input owner")
            return
        if not repo:
            yield self.create_text_message("Please input repo")
            return
        if not issue_number:
            yield self.create_text_message("Please input issue_number")
            return
        if not body:
            yield self.create_text_message("Please input comment body")
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
            url = f"{api_domain}/repos/{owner}/{repo}/issues/{int(issue_number)}/comments"

            payload = {"body": body}

            response = s.request(method="POST", headers=headers, url=url, json=payload)

            # API can return 200 or 201 for success
            if response.status_code in [200, 201]:
                comment = response.json()

                # Safely extract user login
                user_data = comment.get("user", {})
                user_login = user_data.get("login", "") if isinstance(user_data, dict) else ""

                result = {
                    "success": True,
                    "id": comment.get("id"),
                    "user": user_login,
                    "body": comment.get("body", ""),
                    "created_at": datetime.strptime(
                        comment.get("created_at", ""), "%Y-%m-%dT%H:%M:%SZ"
                    ).strftime("%Y-%m-%d %H:%M:%S")
                    if comment.get("created_at")
                    else "",
                    "updated_at": datetime.strptime(
                        comment.get("updated_at", ""), "%Y-%m-%dT%H:%M:%SZ"
                    ).strftime("%Y-%m-%d %H:%M:%S")
                    if comment.get("updated_at")
                    else "",
                    "url": comment.get("html_url", ""),
                }

                s.close()
                yield self.create_text_message(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                s.close()
                handle_github_api_error(response, f"create comment on issue {owner}/{repo}#{issue_number}")
        except InvokeError as e:
            yield self.create_text_message(f"❌ {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"❌ GitHub API request failed: {e}")
