import base64
from collections.abc import Generator
from typing import Any

import requests

from dify_plugin import Tool
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class GithubRepositoryReadmeTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        owner = tool_parameters.get("owner", "")
        repo = tool_parameters.get("repo", "")
        ref = tool_parameters.get("ref", "")
        dir_path = tool_parameters.get("dir", "")
        credential_type = self.runtime.credential_type
        if not owner:
            yield self.create_text_message("Please input owner")
        if not repo:
            yield self.create_text_message("Please input repo")
        if credential_type == CredentialType.API_KEY and "access_tokens" not in self.runtime.credentials:
            yield self.create_text_message("GitHub API Access Tokens is required.")

        if credential_type == CredentialType.OAUTH and "access_tokens" not in self.runtime.credentials:
            yield self.create_text_message("GitHub OAuth Access Tokens is required.")

        access_token = self.runtime.credentials.get("access_tokens")
        try:
            headers = {
                "Content-Type": "application/vnd.github+json",
                "Authorization": f"Bearer {access_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            s = requests.session()
            api_domain = "https://api.github.com"
            url = f"{api_domain}/repos/{owner}/{repo}/readme"
            if dir_path:
                url = f"{url}/{dir_path}"
            if ref:
                url = f"{url}?ref={ref}"
            response = s.request(
                method="GET",
                headers=headers,
                url=url,
            )
            response_data = response.json()
            if response.status_code == 200:
                if response_data.get("encoding") != "base64":
                    raise InvokeError(
                        f"Can not get base64 encoded readme, response encoding is {response_data.get('encoding')}"
                    )
                content = response_data.get("content")
                if not content:
                    raise InvokeError("README content is empty")
                decoded_bytes = base64.b64decode(content)
                decoded_str = decoded_bytes.decode("utf-8")
                yield self.create_text_message(decoded_str)
            else:
                raise InvokeError(f"Request failed: {response.status_code} {response_data.get('message')}")
        except InvokeError as e:
            raise e
        except Exception as e:
            raise InvokeError(f"Request failed: {e}") from e
