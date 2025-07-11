import urllib.parse
from typing import Any, Union, Generator
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class GitlabFilesTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        project = tool_parameters.get("project", "")
        repository = tool_parameters.get("repository", "")
        branch = tool_parameters.get("branch", "")
        path = tool_parameters.get("path", "")
        if not project and (not repository):
            yield self.create_text_message("Either project or repository is required")
        if not branch:
            yield self.create_text_message("Branch is required")
        if not path:
            yield self.create_text_message("Path is required")
        access_token = self.runtime.credentials.get("access_tokens")
        site_url = self.runtime.credentials.get("site_url")
        if "access_tokens" not in self.runtime.credentials or not self.runtime.credentials.get("access_tokens"):
            yield self.create_text_message("Gitlab API Access Tokens is required.")
        if "site_url" not in self.runtime.credentials or not self.runtime.credentials.get("site_url"):
            site_url = "https://gitlab.com"
        ssl_verify = self.runtime.credentials.get("ssl_verify", True)
        result = []
        if repository:
            result = self.fetch_files(site_url, access_token, repository, branch, path, True, ssl_verify)
        else:
            project_id = self.get_project_id(site_url, access_token, repository)
            if project_id:
                result = self.fetch_files(site_url, access_token, project, branch, path, False, ssl_verify)

        for item in result:
            yield self.create_json_message(item)

    def fetch_files(
        self, site_url: str, access_token: str, identifier: str, branch: str, path: str, is_repository: bool, ssl_verify: bool
    ) -> list[dict[str, Any]]:
        domain = site_url
        headers = {"PRIVATE-TOKEN": access_token}
        results = []
        tree_url = None
        try:
            if is_repository:
                encoded_identifier = urllib.parse.quote(identifier, safe="")
                tree_url = f"{domain}/api/v4/projects/{encoded_identifier}/repository/tree?path={path}&ref={branch}"
            else:
                project_id = self.get_project_id(site_url, access_token, identifier)
                if project_id:
                    tree_url = f"{domain}/api/v4/projects/{project_id}/repository/tree?path={path}&ref={branch}"
            if tree_url:
                response = requests.get(tree_url, headers=headers, verify=ssl_verify)
                response.raise_for_status()
                items = response.json()
                for item in items:
                    item_path = item["path"]
                    if item["type"] == "tree":
                        results.extend(
                            self.fetch_files(site_url, access_token, identifier, branch, item_path, is_repository, ssl_verify)
                        )
                    else:
                        encoded_item_path = urllib.parse.quote(item_path, safe="")
                        if is_repository:
                            file_url = f"{domain}/api/v4/projects/{encoded_identifier}/repository/files/{encoded_item_path}/raw?ref={branch}"
                        else:
                            file_url = f"{domain}/api/v4/projects/{project_id}/repository/files{encoded_item_path}/raw?ref={branch}"
                        file_response = requests.get(file_url, headers=headers, verify=ssl_verify)
                        file_response.raise_for_status()
                        file_content = file_response.text
                        results.append({"path": item_path, "branch": branch, "content": file_content})
        except requests.RequestException as e:
            print(f"Error fetching data from GitLab: {e}")
        return results

    def get_project_id(self, site_url: str, access_token: str, project_name: str) -> Union[str, None]:
        headers = {"PRIVATE-TOKEN": access_token}
        try:
            url = f"{site_url}/api/v4/projects?search={project_name}"
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            projects = response.json()
            for project in projects:
                if project["name"] == project_name:
                    return project["id"]
        except requests.RequestException as e:
            print(f"Error fetching project ID from GitLab: {e}")
        return None
