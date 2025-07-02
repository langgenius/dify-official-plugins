import urllib.parse
from typing import Any, Union, Generator
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class GitlabMergeRequestsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        repository = tool_parameters.get("repository", "")
        branch = tool_parameters.get("branch", "")
        start_time = tool_parameters.get("start_time", "")
        end_time = tool_parameters.get("end_time", "")
        state = tool_parameters.get("state", "opened")
        if not repository:
            yield self.create_text_message("Repository is required")
        access_token = self.runtime.credentials.get("access_tokens")
        site_url = self.runtime.credentials.get("site_url")
        if not access_token:
            yield self.create_text_message("Gitlab API Access Tokens is required.")
        if not site_url:
            site_url = "https://gitlab.com"
        ssl_verify = self.runtime.credentials.get("ssl_verify", True)
        result = self.get_merge_requests(site_url, access_token, repository, branch, start_time, end_time, state, ssl_verify)
        for item in result:
            yield self.create_json_message(item)

    def get_merge_requests(
        self, site_url: str, access_token: str, repository: str, branch: str, start_time: str, end_time: str, state: str, ssl_verify: bool
    ) -> list[dict[str, Any]]:
        domain = site_url
        headers = {"PRIVATE-TOKEN": access_token}
        results = []
        try:
            encoded_repository = urllib.parse.quote(repository, safe="")
            merge_requests_url = f"{domain}/api/v4/projects/{encoded_repository}/merge_requests"
            params = {"state": state}
            if start_time:
                params["created_after"] = start_time
            if end_time:
                params["created_before"] = end_time
            response = requests.get(merge_requests_url, headers=headers, params=params, verify=ssl_verify)
            response.raise_for_status()
            merge_requests = response.json()
            for mr in merge_requests:
                if branch and mr["target_branch"] != branch:
                    continue
                results.append(
                    {
                        "id": mr["id"],
                        "title": mr["title"],
                        "author": mr["author"]["name"],
                        "web_url": mr["web_url"],
                        "target_branch": mr["target_branch"],
                        "created_at": mr["created_at"],
                        "state": mr["state"],
                    }
                )
        except requests.RequestException as e:
            print(f"Error fetching merge requests from GitLab: {e}")
        return results
