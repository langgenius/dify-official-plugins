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


class GithubPullCommentsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get comments on a pull request
        """
        owner = tool_parameters.get("owner", "")
        repo = tool_parameters.get("repo", "")
        pull_number = tool_parameters.get("pull_number")
        comment_type = tool_parameters.get("comment_type", "all")
        per_page = tool_parameters.get("per_page", 30)
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

        if credential_type == CredentialType.API_KEY and "access_tokens" not in self.runtime.credentials:
            yield self.create_text_message("GitHub API Access Tokens is required.")
            return

        if credential_type == CredentialType.OAUTH and "access_tokens" not in self.runtime.credentials:
            yield self.create_text_message("GitHub OAuth Access Tokens is required.")
            return

        access_token = self.runtime.credentials.get("access_tokens")
        headers = {
            "Content-Type": "application/vnd.github+json",
            "Authorization": f"Bearer {access_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        api_domain = "https://api.github.com"

        try:
            s = requests.session()
            result = {"issue_comments": [], "review_comments": []}

            # Get issue comments (general comments on the PR)
            if comment_type in ["all", "issue"]:
                issue_url = f"{api_domain}/repos/{owner}/{repo}/issues/{int(pull_number)}/comments"
                response = s.request(method="GET", headers=headers, url=issue_url, params={"per_page": per_page})

                if response.status_code == 200:
                    for comment in response.json():
                        result["issue_comments"].append({
                            "id": comment.get("id"),
                            "user": comment.get("user", {}).get("login", ""),
                            "body": comment.get("body", ""),
                            "created_at": datetime.strptime(
                                comment.get("created_at", ""), "%Y-%m-%dT%H:%M:%SZ"
                            ).strftime("%Y-%m-%d %H:%M:%S") if comment.get("created_at") else "",
                            "updated_at": datetime.strptime(
                                comment.get("updated_at", ""), "%Y-%m-%dT%H:%M:%SZ"
                            ).strftime("%Y-%m-%d %H:%M:%S") if comment.get("updated_at") else "",
                            "url": comment.get("html_url", ""),
                        })
                else:
                    handle_github_api_error(response, f"get issue comments for pull request {owner}/{repo}#{pull_number}")

            # Get review comments (comments on specific lines of code)
            if comment_type in ["all", "review"]:
                review_url = f"{api_domain}/repos/{owner}/{repo}/pulls/{int(pull_number)}/comments"
                response = s.request(method="GET", headers=headers, url=review_url, params={"per_page": per_page})

                if response.status_code == 200:
                    for comment in response.json():
                        result["review_comments"].append({
                            "id": comment.get("id"),
                            "user": comment.get("user", {}).get("login", ""),
                            "body": comment.get("body", ""),
                            "path": comment.get("path", ""),
                            "line": comment.get("line"),
                            "original_line": comment.get("original_line"),
                            "side": comment.get("side", ""),
                            "commit_id": comment.get("commit_id", "")[:7] if comment.get("commit_id") else "",
                            "in_reply_to_id": comment.get("in_reply_to_id"),
                            "created_at": datetime.strptime(
                                comment.get("created_at", ""), "%Y-%m-%dT%H:%M:%SZ"
                            ).strftime("%Y-%m-%d %H:%M:%S") if comment.get("created_at") else "",
                            "updated_at": datetime.strptime(
                                comment.get("updated_at", ""), "%Y-%m-%dT%H:%M:%SZ"
                            ).strftime("%Y-%m-%d %H:%M:%S") if comment.get("updated_at") else "",
                            "url": comment.get("html_url", ""),
                        })
                else:
                    handle_github_api_error(response, f"get review comments for pull request {owner}/{repo}#{pull_number}")

            s.close()

            # Add summary counts
            result["total_issue_comments"] = len(result["issue_comments"])
            result["total_review_comments"] = len(result["review_comments"])

            yield self.create_text_message(json.dumps(result, ensure_ascii=False, indent=2))

        except InvokeError as e:
            yield self.create_text_message(f"❌ {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"❌ GitHub API request failed: {e}")
