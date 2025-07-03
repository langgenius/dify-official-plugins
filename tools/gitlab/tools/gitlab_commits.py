import json
import urllib.parse
from datetime import datetime, timedelta
from typing import Any, Generator
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class GitlabCommitsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        branch = tool_parameters.get("branch", "")
        repository = tool_parameters.get("repository", "")
        employee = tool_parameters.get("employee", "")
        start_time = tool_parameters.get("start_time", "")
        end_time = tool_parameters.get("end_time", "")
        change_type = tool_parameters.get("change_type", "all")
        if not repository:
            yield self.create_text_message("Either repository is required")
        if not start_time:
            start_time = (datetime.utcnow() - timedelta(days=1)).isoformat()
        if not end_time:
            end_time = datetime.utcnow().isoformat()
        access_token = self.runtime.credentials.get("access_tokens")
        site_url = self.runtime.credentials.get("site_url")
        if "access_tokens" not in self.runtime.credentials or not self.runtime.credentials.get("access_tokens"):
            yield self.create_text_message("Gitlab API Access Tokens is required.")
        if "site_url" not in self.runtime.credentials or not self.runtime.credentials.get("site_url"):
            site_url = "https://gitlab.com"
        ssl_verify = self.runtime.credentials.get("ssl_verify", True)
        result = self.fetch_commits(
            site_url, access_token, repository, branch, employee, start_time, end_time, change_type, is_repository=True, ssl_verify=ssl_verify
        )
        for item in result:
            yield self.create_json_message(item)

    def fetch_commits(
        self,
        site_url: str,
        access_token: str,
        repository: str,
        branch: str,
        employee: str,
        start_time: str,
        end_time: str,
        change_type: str,
        is_repository: bool,
        ssl_verify: bool,
    ) -> list[dict[str, Any]]:
        domain = site_url
        headers = {"PRIVATE-TOKEN": access_token}
        results = []
        try:
            encoded_repository = urllib.parse.quote(repository, safe="")
            commits_url = f"{domain}/api/v4/projects/{encoded_repository}/repository/commits"
            params = {"since": start_time, "until": end_time}
            if branch:
                params["ref_name"] = branch
            if employee:
                params["author"] = employee
            commits_response = requests.get(commits_url, headers=headers, params=params, verify=ssl_verify)
            commits_response.raise_for_status()
            commits = commits_response.json()
            for commit in commits:
                commit_sha = commit["id"]
                author_name = commit["author_name"]
                diff_url = f"{domain}/api/v4/projects/{encoded_repository}/repository/commits/{commit_sha}/diff"
                diff_response = requests.get(diff_url, headers=headers, verify=ssl_verify) 
                diff_response.raise_for_status()
                diffs = diff_response.json()
                for diff in diffs:
                    added_lines = diff["diff"].count("\n+")
                    removed_lines = diff["diff"].count("\n-")
                    total_changes = added_lines + removed_lines
                    if change_type == "new":
                        if added_lines > 1:
                            final_code = "".join(
                                [
                                    line[1:]
                                    for line in diff["diff"].split("\n")
                                    if line.startswith("+") and (not line.startswith("+++"))
                                ]
                            )
                            results.append(
                                {
                                    "diff_url": diff_url,
                                    "commit_sha": commit_sha,
                                    "author_name": author_name,
                                    "diff": final_code,
                                }
                            )
                    elif total_changes > 1:
                        final_code = "".join(
                            [
                                line[1:]
                                for line in diff["diff"].split("\n")
                                if (line.startswith("+") or line.startswith("-"))
                                and (not line.startswith("+++"))
                                and (not line.startswith("---"))
                            ]
                        )
                        final_code_escaped = json.dumps(final_code)[1:-1]
                        results.append(
                            {
                                "diff_url": diff_url,
                                "commit_sha": commit_sha,
                                "author_name": author_name,
                                "diff": final_code_escaped,
                            }
                        )
        except requests.RequestException as e:
            print(f"Error fetching data from GitLab: {e}")
        return results
