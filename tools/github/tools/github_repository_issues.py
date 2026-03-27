import json
from collections.abc import Generator
from datetime import datetime
from typing import Any

import requests

from dify_plugin import Tool
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class GithubRepositoryIssuesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        owner = tool_parameters.get("owner", "")
        repo = tool_parameters.get("repo", "")
        state = tool_parameters.get("state", "open")
        per_page = tool_parameters.get("per_page", 10)
        sort = tool_parameters.get("sort", "created")
        direction = tool_parameters.get("direction", "desc")

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
            url = f"{api_domain}/repos/{owner}/{repo}/issues"

            params = {"state": state, "per_page": per_page, "sort": sort, "direction": direction}

            response = s.request(
                method="GET",
                headers=headers,
                url=url,
                params=params,
            )

            if response.status_code == 200:
                response_data = response.json()

                issues = []
                for issue in response_data:
                    # Skip pull requests (they also appear in issues API)
                    if issue.get("pull_request"):
                        continue

                    issue_info = {
                        "number": issue.get("number", 0),
                        "title": issue.get("title", ""),
                        "body": (issue.get("body", "") or "")[:200] + "..."
                        if len(issue.get("body", "") or "") > 200
                        else (issue.get("body", "") or ""),
                        "state": issue.get("state", ""),
                        "url": issue.get("html_url", ""),
                        "user": issue.get("user", {}).get("login", ""),
                        "assignee": issue.get("assignee", {}).get("login", "") if issue.get("assignee") else "",
                        "labels": [label.get("name", "") for label in issue.get("labels", [])],
                        "comments": issue.get("comments", 0),
                        "created_at": datetime.strptime(issue.get("created_at", ""), "%Y-%m-%dT%H:%M:%SZ").strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if issue.get("created_at")
                        else "",
                        "updated_at": datetime.strptime(issue.get("updated_at", ""), "%Y-%m-%dT%H:%M:%SZ").strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if issue.get("updated_at")
                        else "",
                    }
                    issues.append(issue_info)

                s.close()

                if not issues:
                    yield self.create_text_message(f"No {state} issues found in {owner}/{repo}")
                else:
                    yield self.create_text_message(
                        self.session.model.summary.invoke(
                            text=json.dumps(issues, ensure_ascii=False),
                            instruction="Summarize the GitHub issues in a structured format",
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
