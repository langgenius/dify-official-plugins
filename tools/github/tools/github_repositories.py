import json
from collections.abc import Generator
from datetime import datetime
from typing import Any
from urllib.parse import quote

import requests

from dify_plugin import Tool
from dify_plugin.entities import I18nObject, ParameterOption
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.tool import ToolInvokeMessage


class GithubRepositoriesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        top_n = tool_parameters.get("top_n", 5)
        query = tool_parameters.get("query", "")
        credential_type = self.runtime.credential_type
        if not query:
            yield self.create_text_message("Please input symbol")

        if credential_type == CredentialType.API_KEY and "access_tokens" not in self.runtime.credentials:
            yield self.create_text_message("GitHub API Access Tokens is required.")

        if credential_type == CredentialType.OAUTH and "access_tokens" not in self.runtime.credentials:
            yield self.create_text_message("GitHub OAuth Access Tokens is required.")

        access_token = self.runtime.credentials.get("access_tokens")
        try:
            headers = {
                "Content-Type": "application/vnd.github+json",
                "Authorization": f"Bearer {access_token}",
                # fixed api version
                "X-GitHub-Api-Version": "2022-11-28",
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
                                item["description"][:100] + "..."
                                if len(item["description"]) > 100
                                else item["description"]
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
                        self.session.model.summary.invoke(
                            text=json.dumps(contents, ensure_ascii=False),
                            instruction="Summarize the text",
                        )
                    )
                else:
                    yield self.create_text_message(f"No items related to {query} were found.")
            else:
                yield self.create_text_message(response.json().get("message"))
        except Exception as e:
            yield self.create_text_message(f"GitHub API Key and Api Version is invalid. {e}")

    def _fetch_parameter_options(self, parameter: str) -> list[ParameterOption]:
        return [
            ParameterOption(
                value="iamjoel",
                label=I18nObject(en_US="Joel"),
                icon="https://avatars.githubusercontent.com/u/2120155?s=40&v=4",
            ),
            ParameterOption(
                value="yeuoly",
                label=I18nObject(en_US="Yeuoly"),
                icon="https://avatars.githubusercontent.com/u/45712896?s=60&v=4",
            ),
        ]
