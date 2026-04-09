import json
from collections.abc import Generator
from datetime import datetime
from typing import Any

import requests

from dify_plugin import Tool
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class GithubRepositoryPullsTool(Tool):
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
            url = f"{api_domain}/repos/{owner}/{repo}/pulls"

            params = {"state": state, "per_page": per_page, "sort": sort, "direction": direction}

            response = s.request(
                method="GET",
                headers=headers,
                url=url,
                params=params,
            )

            if response.status_code == 200:
                response_data = response.json()

                pulls = []
                for pull in response_data:
                    pull_info = {
                        "number": pull.get("number", 0),
                        "title": pull.get("title", ""),
                        "body": (pull.get("body", "") or "")[:200] + "..."
                        if len(pull.get("body", "") or "") > 200
                        else (pull.get("body", "") or ""),
                        "state": pull.get("state", ""),
                        "url": pull.get("html_url", ""),
                        "user": pull.get("user", {}).get("login", ""),
                        "assignee": pull.get("assignee", {}).get("login", "") if pull.get("assignee") else "",
                        "labels": [label.get("name", "") for label in pull.get("labels", [])],
                        "comments": pull.get("comments", 0),
                        "review_comments": pull.get("review_comments", 0),
                        "commits": pull.get("commits", 0),
                        "additions": pull.get("additions", 0),
                        "deletions": pull.get("deletions", 0),
                        "changed_files": pull.get("changed_files", 0),
                        "mergeable": pull.get("mergeable", None),
                        "merged": pull.get("merged", False),
                        "draft": pull.get("draft", False),
                        "head": {
                            "ref": pull.get("head", {}).get("ref", ""),
                            "sha": pull.get("head", {}).get("sha", "")[:7],
                        },
                        "base": {
                            "ref": pull.get("base", {}).get("ref", ""),
                            "sha": pull.get("base", {}).get("sha", "")[:7],
                        },
                        "created_at": datetime.strptime(pull.get("created_at", ""), "%Y-%m-%dT%H:%M:%SZ").strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if pull.get("created_at")
                        else "",
                        "updated_at": datetime.strptime(pull.get("updated_at", ""), "%Y-%m-%dT%H:%M:%SZ").strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if pull.get("updated_at")
                        else "",
                    }
                    pulls.append(pull_info)

                s.close()

                if not pulls:
                    yield self.create_text_message(f"No {state} pull requests found in {owner}/{repo}")
                else:
                    yield self.create_text_message(
                        self.session.model.summary.invoke(
                            text=json.dumps(pulls, ensure_ascii=False),
                            instruction="Summarize the GitHub pull requests in a structured format",
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
