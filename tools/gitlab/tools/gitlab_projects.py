import urllib.parse
from typing import Any, Union, Generator
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class GitlabProjectsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        project_name = tool_parameters.get("project_name", "")
        page = tool_parameters.get("page", 1)
        page_size = tool_parameters.get("page_size", 20)
        access_token = self.runtime.credentials.get("access_tokens")
        site_url = self.runtime.credentials.get("site_url")
        if not access_token:
            yield self.create_text_message("Gitlab API Access Tokens is required.")
        if not site_url:
            site_url = "https://gitlab.com"
        ssl_verify = self.runtime.credentials.get("ssl_verify", True)
        result = self.fetch_projects(site_url, access_token, project_name, page, page_size, ssl_verify)
        for item in result:
            yield self.create_json_message(item)

    def fetch_projects(
        self, site_url: str, access_token: str, project_name: str, page: str, page_size: str, ssl_verify: bool
    ) -> list[dict[str, Any]]:
        domain = site_url
        headers = {"PRIVATE-TOKEN": access_token}
        results = []
        try:
            if project_name:
                encoded_project_name = urllib.parse.quote(project_name, safe="")
                projects_url = (
                    f"{domain}/api/v4/projects?search={encoded_project_name}&page={page}&per_page={page_size}"
                )
            else:
                projects_url = f"{domain}/api/v4/projects?page={page}&per_page={page_size}"
            response = requests.get(projects_url, headers=headers, verify=ssl_verify)
            response.raise_for_status()
            projects = response.json()
            for project in projects:
                if project_name and project["name"].lower() == project_name.lower():
                    results.append(
                        {
                            "id": project["id"],
                            "name": project["name"],
                            "description": project.get("description", ""),
                            "web_url": project["web_url"],
                        }
                    )
                elif not project_name:
                    results.append(
                        {
                            "id": project["id"],
                            "name": project["name"],
                            "description": project.get("description", ""),
                            "web_url": project["web_url"],
                        }
                    )
        except requests.RequestException as e:
            print(f"Error fetching data from GitLab: {e}")
        return results
