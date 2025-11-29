import base64
import json
from collections.abc import Generator
from typing import Any

import requests

from dify_plugin import Tool
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class GithubRepositoryContentsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        owner = tool_parameters.get("owner", "")
        repo = tool_parameters.get("repo", "")
        path = tool_parameters.get("path", "")
        ref = tool_parameters.get("ref", "")

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
            url = f"{api_domain}/repos/{owner}/{repo}/contents"

            if path:
                url = f"{url}/{path}"

            params = {}
            if ref:
                params["ref"] = ref

            response = s.request(
                method="GET",
                headers=headers,
                url=url,
                params=params,
            )

            if response.status_code == 200:
                response_data = response.json()

                # Handle both single file and directory listings
                if isinstance(response_data, list):
                    # Directory listing
                    contents = []
                    for item in response_data:
                        content_info = {
                            "name": item.get("name", ""),
                            "path": item.get("path", ""),
                            "type": item.get("type", ""),
                            "size": item.get("size", 0),
                            "sha": item.get("sha", ""),
                            "url": item.get("html_url", ""),
                            "download_url": item.get("download_url", ""),
                            "git_url": item.get("git_url", ""),
                        }
                        contents.append(content_info)

                    result = {"type": "directory", "path": path or "/", "contents": contents}

                    yield self.create_text_message(
                        self.session.model.summary.invoke(
                            text=json.dumps(result, ensure_ascii=False),
                            instruction="Summarize the GitHub repository contents in a structured format",
                        )
                    )
                else:
                    # Single file
                    if response_data.get("type") == "file":
                        file_info = {
                            "name": response_data.get("name", ""),
                            "path": response_data.get("path", ""),
                            "type": response_data.get("type", ""),
                            "size": response_data.get("size", 0),
                            "sha": response_data.get("sha", ""),
                            "url": response_data.get("html_url", ""),
                            "download_url": response_data.get("download_url", ""),
                            "encoding": response_data.get("encoding", ""),
                        }

                        # Try to decode content if it's base64 encoded and small enough
                        if (
                            response_data.get("encoding") == "base64"
                            and response_data.get("content")
                            and response_data.get("size", 0) < 100000
                        ):  # Only decode files < 100KB
                            try:
                                content = response_data.get("content", "").replace("\n", "")
                                decoded_content = base64.b64decode(content).decode("utf-8")
                                file_info["content"] = (
                                    decoded_content[:2000] + "..." if len(decoded_content) > 2000 else decoded_content
                                )
                            except Exception:
                                file_info["content"] = "Unable to decode content"

                        result = {"type": "file", "file_info": file_info}

                        yield self.create_text_message(
                            self.session.model.summary.invoke(
                                text=json.dumps(result, ensure_ascii=False),
                                instruction="Summarize the GitHub file content in a structured format",
                            )
                        )
                    else:
                        yield self.create_text_message(f"Content type '{response_data.get('type')}' is not supported")

                s.close()
            else:
                response_data = response.json()
                raise InvokeError(
                    f"Request failed: {response.status_code} {response_data.get('message', 'Unknown error')}"
                )
        except InvokeError as e:
            raise e
        except Exception as e:
            raise InvokeError(f"GitHub API request failed: {e}") from e
