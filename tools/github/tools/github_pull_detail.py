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


class GithubPullDetailTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get detailed information about a specific pull request
        """
        owner = tool_parameters.get("owner", "")
        repo = tool_parameters.get("repo", "")
        pull_number = tool_parameters.get("pull_number")
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
        try:
            headers = {
                "Content-Type": "application/vnd.github+json",
                "Authorization": f"Bearer {access_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            s = requests.session()
            api_domain = "https://api.github.com"
            url = f"{api_domain}/repos/{owner}/{repo}/pulls/{int(pull_number)}"

            response = s.request(method="GET", headers=headers, url=url)

            if response.status_code == 200:
                pull = response.json()

                pull_info = {
                    "number": pull.get("number", 0),
                    "title": pull.get("title", ""),
                    "body": pull.get("body", "") or "",
                    "state": pull.get("state", ""),
                    "url": pull.get("html_url", ""),
                    "diff_url": pull.get("diff_url", ""),
                    "patch_url": pull.get("patch_url", ""),
                    "user": pull.get("user", {}).get("login", ""),
                    "assignees": [a.get("login", "") for a in pull.get("assignees", [])],
                    "reviewers": [r.get("login", "") for r in pull.get("requested_reviewers", [])],
                    "labels": [label.get("name", "") for label in pull.get("labels", [])],
                    "milestone": pull.get("milestone", {}).get("title", "") if pull.get("milestone") else "",
                    "comments": pull.get("comments", 0),
                    "review_comments": pull.get("review_comments", 0),
                    "commits": pull.get("commits", 0),
                    "additions": pull.get("additions", 0),
                    "deletions": pull.get("deletions", 0),
                    "changed_files": pull.get("changed_files", 0),
                    "mergeable": pull.get("mergeable"),
                    "mergeable_state": pull.get("mergeable_state", ""),
                    "merged": pull.get("merged", False),
                    "merged_by": pull.get("merged_by", {}).get("login", "") if pull.get("merged_by") else "",
                    "merge_commit_sha": pull.get("merge_commit_sha", ""),
                    "draft": pull.get("draft", False),
                    "head": {
                        "ref": pull.get("head", {}).get("ref", ""),
                        "sha": pull.get("head", {}).get("sha", ""),
                        "repo": pull.get("head", {}).get("repo", {}).get("full_name", "") if pull.get("head", {}).get("repo") else "",
                    },
                    "base": {
                        "ref": pull.get("base", {}).get("ref", ""),
                        "sha": pull.get("base", {}).get("sha", ""),
                        "repo": pull.get("base", {}).get("repo", {}).get("full_name", "") if pull.get("base", {}).get("repo") else "",
                    },
                    "created_at": datetime.strptime(pull.get("created_at", ""), "%Y-%m-%dT%H:%M:%SZ").strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ) if pull.get("created_at") else "",
                    "updated_at": datetime.strptime(pull.get("updated_at", ""), "%Y-%m-%dT%H:%M:%SZ").strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ) if pull.get("updated_at") else "",
                    "closed_at": datetime.strptime(pull.get("closed_at", ""), "%Y-%m-%dT%H:%M:%SZ").strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ) if pull.get("closed_at") else "",
                    "merged_at": datetime.strptime(pull.get("merged_at", ""), "%Y-%m-%dT%H:%M:%SZ").strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ) if pull.get("merged_at") else "",
                }

                s.close()
                yield self.create_text_message(json.dumps(pull_info, ensure_ascii=False, indent=2))
            else:
                handle_github_api_error(response, f"get pull request {owner}/{repo}#{pull_number}")
        except InvokeError as e:
            yield self.create_text_message(f"❌ {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"❌ GitHub API request failed: {e}")
