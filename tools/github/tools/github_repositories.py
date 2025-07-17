import json
from datetime import datetime
from typing import Any, Generator
from urllib.parse import quote

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class GithubRepositoriesTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        top_n = tool_parameters.get("top_n", 5)
        query = tool_parameters.get("query", "")
        if not query:
            yield self.create_text_message("Please input symbol")
        if "access_tokens" not in self.runtime.credentials or not self.runtime.credentials.get("access_tokens"):
            yield self.create_text_message("GitHub API Access Tokens is required.")
        if "api_version" not in self.runtime.credentials or not self.runtime.credentials.get("api_version"):
            api_version = "2022-11-28"
        else:
            api_version = self.runtime.credentials.get("api_version")
        try:
            headers = {
                "Content-Type": "application/vnd.github+json",
                "Authorization": f"Bearer {self.runtime.credentials.get('access_tokens')}",
                "X-GitHub-Api-Version": api_version,
            }
            with requests.session() as s:
                api_domain = "https://api.github.com"
                response = s.request(
                    method="GET",
                    headers=headers,
                    url=f"{api_domain}/search/repositories?q={quote(query)}&sort=stars&per_page={top_n}&order=desc",
                )
                response_text = response.text
                if response.status_code == 200:
                    response_data = json.loads(response_text) if response_text else {}
                    yield self.create_json_message(
                        json=response_data
                    )
                else:
                    yield self.create_text_message(response_text)
        except Exception as e:
            yield self.create_text_message(f"Failed to fetch GitHub repositories: {str(e)}")
