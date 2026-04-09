import json
from collections.abc import Generator
from typing import Any

import requests

from dify_plugin import Tool
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class GithubSearchCodeTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        query = tool_parameters.get("query", "")
        per_page = tool_parameters.get("per_page", 10)
        sort = tool_parameters.get("sort", "")
        order = tool_parameters.get("order", "desc")

        credential_type = self.runtime.credential_type

        if not query:
            yield self.create_text_message("Please input search query")
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
            url = f"{api_domain}/search/code"

            params = {"q": query, "per_page": per_page, "order": order}

            if sort:
                params["sort"] = sort

            response = s.request(
                method="GET",
                headers=headers,
                url=url,
                params=params,
            )

            if response.status_code == 200:
                response_data = response.json()

                total_count = response_data.get("total_count", 0)
                items = response_data.get("items", [])

                search_results = []
                for item in items:
                    result_info = {
                        "name": item.get("name", ""),
                        "path": item.get("path", ""),
                        "sha": item.get("sha", "")[:7],
                        "url": item.get("html_url", ""),
                        "git_url": item.get("git_url", ""),
                        "download_url": item.get("download_url", ""),
                        "score": item.get("score", 0),
                        "repository": {
                            "id": item.get("repository", {}).get("id", 0),
                            "name": item.get("repository", {}).get("name", ""),
                            "full_name": item.get("repository", {}).get("full_name", ""),
                            "url": item.get("repository", {}).get("html_url", ""),
                            "description": item.get("repository", {}).get("description", ""),
                            "language": item.get("repository", {}).get("language", ""),
                            "stars": item.get("repository", {}).get("stargazers_count", 0),
                            "forks": item.get("repository", {}).get("forks_count", 0),
                            "is_private": item.get("repository", {}).get("private", False),
                            "owner": {
                                "login": item.get("repository", {}).get("owner", {}).get("login", ""),
                                "type": item.get("repository", {}).get("owner", {}).get("type", ""),
                            },
                        },
                        "text_matches": [
                            {
                                "fragment": match.get("fragment", ""),
                                "matches": [
                                    {"text": m.get("text", ""), "indices": m.get("indices", [])}
                                    for m in match.get("matches", [])
                                ],
                            }
                            for match in item.get("text_matches", [])
                        ],
                    }
                    search_results.append(result_info)

                result = {"total_count": total_count, "query": query, "results": search_results}

                s.close()

                if not search_results:
                    yield self.create_text_message(f"No code found for query: {query}")
                else:
                    yield self.create_text_message(
                        self.session.model.summary.invoke(
                            text=json.dumps(result, ensure_ascii=False),
                            instruction="Summarize the GitHub code search results in a structured format",
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
