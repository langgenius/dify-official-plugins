import json
from datetime import datetime
from typing import Any, Generator
from urllib.parse import quote
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


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
            s = requests.session()
            api_domain = "https://api.github.com"
            response = s.request(
                method="GET",
                headers=headers,
                url=f"{api_domain}/search/repositories?q={quote(query)}&sort=stars&per_page={top_n}&order=desc",
            )
            response_data = response.json()
            if response.status_code == 200 and isinstance(response_data.get("items"), list):
                contents = []
                if len(response_data.get("items")) > 0:
                    for item in response_data.get("items"):
                        content = {}
                        updated_at_object = datetime.strptime(item["updated_at"], "%Y-%m-%dT%H:%M:%SZ")
                        content["owner"] = item["owner"]["login"]
                        content["name"] = item["name"]
                        if item["description"] is not None:
                            content["description"] = (
                                item["description"][:100] + "..." if len(item["description"]) > 100 else item["description"]
                            )
                        else:
                            content["description"] = ""
                        content["url"] = item["html_url"]
                        content["star"] = item["watchers"]
                        content["forks"] = item["forks"]
                        content["updated"] = updated_at_object.strftime("%Y-%m-%d")
                        contents.append(content)
                    s.close()
                    yield self.create_text_message(
                        self.session.model.summary(content=json.dumps(contents, ensure_ascii=False))
                    )
                else:
                    yield self.create_text_message(f"No items related to {query} were found.")
            else:
                yield self.create_text_message(response.json().get("message"))
        except Exception as e:
            yield self.create_text_message("GitHub API Key and Api Version is invalid. {}".format(e))
