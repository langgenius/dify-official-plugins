import json
from collections.abc import Generator
from typing import Any

import requests

from dify_plugin import Tool
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError

from .github_error_handler import handle_github_api_error


class GithubPullFilesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get the list of files changed in a pull request
        """
        owner = tool_parameters.get("owner", "")
        repo = tool_parameters.get("repo", "")
        pull_number = tool_parameters.get("pull_number")
        per_page = tool_parameters.get("per_page", 30)
        include_patch = tool_parameters.get("include_patch", False)
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
            url = f"{api_domain}/repos/{owner}/{repo}/pulls/{int(pull_number)}/files"

            params = {"per_page": per_page}
            response = s.request(method="GET", headers=headers, url=url, params=params)

            if response.status_code == 200:
                files_data = response.json()

                files = []
                for file in files_data:
                    file_info = {
                        "filename": file.get("filename", ""),
                        "status": file.get("status", ""),  # added, removed, modified, renamed, copied, changed, unchanged
                        "additions": file.get("additions", 0),
                        "deletions": file.get("deletions", 0),
                        "changes": file.get("changes", 0),
                        "blob_url": file.get("blob_url", ""),
                        "raw_url": file.get("raw_url", ""),
                    }

                    # Include previous filename for renamed files
                    if file.get("previous_filename"):
                        file_info["previous_filename"] = file.get("previous_filename")

                    # Include patch content if requested
                    if include_patch and file.get("patch"):
                        file_info["patch"] = file.get("patch", "")

                    files.append(file_info)

                s.close()

                result = {
                    "total_files": len(files),
                    "files": files,
                }

                yield self.create_text_message(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                handle_github_api_error(response, f"get files for pull request {owner}/{repo}#{pull_number}")
        except InvokeError as e:
            yield self.create_text_message(f"❌ {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"❌ GitHub API request failed: {e}")
