import base64
from typing import Any, Generator

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class GithubRepositoryReadmeTool(Tool):
    def _invoke(
            self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        owner = tool_parameters.get("owner", "")
        repo = tool_parameters.get("repo", "")
        ref = tool_parameters.get("ref", "")
        dir_path = tool_parameters.get("dir", "")
        if not owner:
            yield self.create_text_message("Please input owner")
        if not repo:
            yield self.create_text_message("Please input repo")
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
                if "base64" != response_data.get("encoding"):
                    raise InvokeError(
                        f"Can not get base64 encoded readme, response encoding is {response_data.get('encoding')}")
                content = response_data.get("content")
                if not content:
                    raise InvokeError("README content is empty")
                decoded_bytes = base64.b64decode(content)
                decoded_str = decoded_bytes.decode('utf-8')
                yield self.create_text_message(decoded_str)
            else:
                raise InvokeError(f"Request failed: {response.status_code} {response_data.get('message')}")
        except InvokeError as e:
            raise e
        except Exception as e:
            raise InvokeError(f"Request failed: {e}")
