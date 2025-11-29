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


class GithubCreatePullReviewTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a review on a pull request
        """
        owner = tool_parameters.get("owner", "")
        repo = tool_parameters.get("repo", "")
        pull_number = tool_parameters.get("pull_number")
        event = tool_parameters.get("event", "").upper()
        body = tool_parameters.get("body", "")
        commit_id = tool_parameters.get("commit_id", "")
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
        if not event:
            yield self.create_text_message("Please input event (APPROVE, REQUEST_CHANGES, or COMMENT)")
            return

        # Validate event
        valid_events = ["APPROVE", "REQUEST_CHANGES", "COMMENT"]
        if event not in valid_events:
            yield self.create_text_message(f"Invalid event. Must be one of: {', '.join(valid_events)}")
            return

        # Body is required for REQUEST_CHANGES and COMMENT
        if event in ["REQUEST_CHANGES", "COMMENT"] and not body:
            yield self.create_text_message(f"Body is required when event is {event}")
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
            url = f"{api_domain}/repos/{owner}/{repo}/pulls/{int(pull_number)}/reviews"

            payload = {"event": event}
            if body:
                payload["body"] = body
            if commit_id:
                payload["commit_id"] = commit_id

            response = s.request(method="POST", headers=headers, url=url, json=payload)

            # API can return 200 or 201 for success
            if response.status_code in [200, 201]:
                review = response.json()

                # Safely extract user login
                user_data = review.get("user", {})
                user_login = user_data.get("login", "") if isinstance(user_data, dict) else ""

                result = {
                    "success": True,
                    "id": review.get("id"),
                    "user": user_login,
                    "state": review.get("state", ""),
                    "body": review.get("body", "") or "",
                    "commit_id": review.get("commit_id", "")[:7] if review.get("commit_id") else "",
                    "submitted_at": datetime.strptime(review.get("submitted_at", ""), "%Y-%m-%dT%H:%M:%SZ").strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if review.get("submitted_at")
                    else "",
                    "url": review.get("html_url", ""),
                }

                s.close()
                yield self.create_text_message(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                s.close()
                handle_github_api_error(response, f"create review for pull request {owner}/{repo}#{pull_number}")
        except InvokeError as e:
            yield self.create_text_message(f"❌ {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"❌ GitHub API request failed: {e}")
