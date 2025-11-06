import urllib.parse
from typing import Any, Generator, Union

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


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
            project_id = self.get_project_id(site_url, access_token, project)
            if project_id:
                result = self.fetch_files(site_url, access_token, project, branch, path, False, ssl_verify)

        for item in result:
            yield self.create_json_message(item)

    def fetch_files(
        self, site_url: str, access_token: str, identifier: str, branch: str, path: str, is_repository: bool, ssl_verify: bool
    ) -> list[dict[str, Any]]:
        domain = site_url
        headers = {"PRIVATE-TOKEN": access_token}
        results: list[dict[str, Any]] = []

        try:
            encoded_identifier = urllib.parse.quote(identifier, safe="") if is_repository else None
            project_id: Union[str, None]
            if is_repository:
                project_id = None
            else:
                project_id = self.get_project_id(site_url, access_token, identifier)
                if not project_id:
                    return results

            project_reference = encoded_identifier if is_repository else str(project_id)

            def build_tree_url(target_path: str) -> str:
                encoded_path = urllib.parse.quote(target_path, safe="/") if target_path else ""
                query_path = f"&path={encoded_path}" if target_path else ""
                return f"{domain}/api/v4/projects/{project_reference}/repository/tree?ref={branch}{query_path}"

            def build_file_url(target_path: str) -> str:
                encoded_path = urllib.parse.quote(target_path, safe="")
                return (
                    f"{domain}/api/v4/projects/{project_reference}/repository/files/{encoded_path}/raw?ref={branch}"
                )

            def fetch_directory(target_path: str) -> Union[list[dict[str, Any]], None]:
                tree_url = build_tree_url(target_path)
                response = requests.get(tree_url, headers=headers, verify=ssl_verify)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()

            def fetch_file(target_path: str) -> Union[dict[str, Any], None]:
                if not target_path:
                    return None
                file_url = build_file_url(target_path)
                response = requests.get(file_url, headers=headers, verify=ssl_verify)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return {"path": target_path, "branch": branch, "content": response.text}

            def walk_path(target_path: str) -> list[dict[str, Any]]:
                directory_items = fetch_directory(target_path)
                if directory_items is None:
                    file_result = fetch_file(target_path)
                    return [file_result] if file_result else []

                collected: list[dict[str, Any]] = []
                for item in directory_items:
                    item_path = item["path"]
                    if item["type"] == "tree":
                        collected.extend(walk_path(item_path))
                    else:
                        file_result = fetch_file(item_path)
                        if file_result:
                            collected.append(file_result)
                return collected

            results = walk_path(path)
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
