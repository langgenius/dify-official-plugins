from collections.abc import Generator
import requests
import time
import base64
import markdown
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

from dify_plugin.entities.datasource import (
    DatasourceGetPagesResponse,
    DatasourceMessage,
    GetOnlineDocumentPageContentRequest,
    OnlineDocumentInfo,
)
from dify_plugin.interfaces.datasource.online_document import OnlineDocumentDatasource


class GitHubDataSource(OnlineDocumentDatasource):
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.base_url = "https://api.github.com"
        
    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers"""
        credentials = self.runtime.credentials
        access_token = credentials.get("access_token")
        
        return {
            "Authorization": f"token {access_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Dify-GitHub-Datasource"
        }
    
    def _handle_rate_limit(self, response: requests.Response) -> None:
        """Handle API rate limiting"""
        if response.status_code == 403:
            rate_limit_remaining = response.headers.get("X-RateLimit-Remaining", "0")
            if rate_limit_remaining == "0":
                reset_time = int(response.headers.get("X-RateLimit-Reset", "0"))
                current_time = int(time.time())
                sleep_time = max(reset_time - current_time + 1, 60)
                raise ValueError(f"GitHub API rate limit exceeded. Please wait {sleep_time} seconds.")
        elif response.status_code == 401:
            raise ValueError("Invalid GitHub access token. Please check your credentials.")
        elif response.status_code >= 400:
            raise ValueError(f"GitHub API error: {response.status_code} - {response.text}")
    
    def _make_request(self, url: str, params: Optional[Dict] = None) -> Dict:
        """Make API request and handle errors"""
        headers = self._get_headers()
        response = requests.get(url, headers=headers, params=params, timeout=30)
        self._handle_rate_limit(response)
        return response.json()
    
    def _get_pages(self, datasource_parameters: dict[str, Any]) -> DatasourceGetPagesResponse:
        """Get GitHub page list (repositories, Issues, PRs)"""
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            raise ValueError("Access token not found in credentials")
        
        # Get user information
        user_info = self._make_request(f"{self.base_url}/user")
        workspace_name = f"{user_info.get('name', user_info.get('login'))}'s GitHub"
        workspace_icon = user_info.get('avatar_url', '')
        workspace_id = str(user_info.get('id', ''))
        
        pages = []
        visibility = datasource_parameters.get("visibility", "all")
        if visibility not in {"all", "public", "private"}:
            raise ValueError(f"Invalid 'visibility' parameter: {visibility}. Allowed values are: all, public, private.")

        affiliation = datasource_parameters.get("affiliation", "owner,collaborator,organization_member")
        if affiliation:
            allowed_affiliations = {"owner", "collaborator", "organization_member"}
            parts = {p.strip() for p in affiliation.split(',') if p.strip()}
            if not parts and affiliation.strip():
                raise ValueError(f"Invalid 'affiliation' parameter: '{affiliation}' resolved to an empty set.")
            if not parts.issubset(allowed_affiliations):
                raise ValueError(
                    f"Invalid 'affiliation' parts: {', '.join(parts - allowed_affiliations)}. Allowed: {', '.join(allowed_affiliations)}.")

        _type = datasource_parameters.get("type")
        if _type and _type not in {"all", "owner", "public", "private", "member"}:
            raise ValueError(
                f"Invalid 'type' parameter: {_type}. Allowed values are: all, owner, public, private, member.")
        
        # Get user repositories
        repos = self._get_repositories(visibility=visibility, affiliation=affiliation, _type=_type)
        for repo in repos:
            # Add repository as page
            pages.append({
                "page_id": f"repo:{repo['full_name']}",
                "page_name": repo['name'],
                "last_edited_time": repo.get("updated_at", ""),
                "type": "repository",
                "url": repo['html_url'],
                "metadata": {
                    "description": repo.get("description", ""),
                    "language": repo.get("language", ""),
                    "stars": repo.get("stargazers_count", 0),
                    "updated_at": repo.get("updated_at", ""),
                    "private": repo.get("private", False)
                }
            })
            
            # Add README file (if exists)
            try:
                readme_info = self._make_request(f"{self.base_url}/repos/{repo['full_name']}/readme")
                pages.append({
                    "page_id": f"file:{repo['full_name']}:README.md",
                    "page_name": f"{repo['name']} - README",
                    "last_edited_time": repo.get("updated_at", ""),
                    "type": "file",
                    "url": readme_info.get('html_url', ''),
                    "metadata": {
                        "repository": repo['full_name'],
                        "file_path": "README.md",
                        "size": readme_info.get('size', 0)
                    }
                })
            except ValueError:
                pass  # README doesn't exist
            
            # Add popular Issues
            try:
                issues = self._make_request(
                    f"{self.base_url}/repos/{repo['full_name']}/issues",
                    params={"state": "all", "per_page": 5, "sort": "updated"}
                )
                for issue in issues:
                    if "pull_request" not in issue:  # Exclude PRs
                        pages.append({
                            "page_id": f"issue:{repo['full_name']}:{issue['number']}",
                            "page_name": f"Issue #{issue['number']}: {issue['title']}",
                            "last_edited_time": issue.get('updated_at', ''),
                            "type": "issue",
                            "url": issue['html_url'],
                            "metadata": {
                                "repository": repo['full_name'],
                                "issue_number": issue['number'],
                                "state": issue['state'],
                                "author": issue['user']['login'],
                                "created_at": issue['created_at']
                            }
                        })
            except ValueError:
                pass  # Issues access failed
            
            # Add popular PRs
            try:
                prs = self._make_request(
                    f"{self.base_url}/repos/{repo['full_name']}/pulls",
                    params={"state": "all", "per_page": 5, "sort": "updated"}
                )
                for pr in prs:
                    pages.append({
                        "page_id": f"pr:{repo['full_name']}:{pr['number']}",
                        "page_name": f"PR #{pr['number']}: {pr['title']}",
                        "last_edited_time": pr.get('updated_at', ''),
                        "type": "pull_request",
                        "url": pr['html_url'],
                        "metadata": {
                            "repository": repo['full_name'],
                            "pr_number": pr['number'],
                            "state": pr['state'],
                            "author": pr['user']['login'],
                            "base_branch": pr['base']['ref'],
                            "head_branch": pr['head']['ref']
                        }
                    })
            except ValueError:
                pass  # PRs access failed
        
        online_document_info = OnlineDocumentInfo(
            workspace_name=workspace_name,
            workspace_icon=workspace_icon,
            workspace_id=workspace_id,
            pages=pages,
            total=len(pages),
        )
        
        return DatasourceGetPagesResponse(result=[online_document_info])
    
    def _get_repositories(self,
                          max_repos: int = 20,
                          visibility: str | None = None,
                          affiliation: str | None = None,
                          _type: str | None = None) -> List[Dict]:
        """Get user repository list"""
        params = {"per_page": max_repos, "sort": "updated", "direction": "desc"}
        if visibility:
            params["visibility"] = visibility
        if affiliation:
            params["affiliation"] = affiliation
        if _type:
            params["type"] = _type
        repos = self._make_request(f"{self.base_url}/user/repos", params)
        return repos
    
    def _get_content(self, page: GetOnlineDocumentPageContentRequest) -> Generator[DatasourceMessage, None, None]:
        """Get page content"""
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            raise ValueError("Access token not found in credentials")
        
        page_id = page.page_id
        
        if page_id.startswith("repo:"):
            # Get repository information
            yield from self._get_repository_content(page_id)
        elif page_id.startswith("file:"):
            # Get file content
            yield from self._get_file_content(page_id)
        elif page_id.startswith("issue:"):
            # Get Issue content
            yield from self._get_issue_content(page_id)
        elif page_id.startswith("pr:"):
            # Get PR content
            yield from self._get_pr_content(page_id)
        else:
            raise ValueError(f"Unsupported page type: {page_id}")
    
    def _get_repository_content(self, page_id: str) -> Generator[DatasourceMessage, None, None]:
        """Get repository information content"""
        repo_name = page_id[5:]  # Remove "repo:" prefix
        
        repo_info = self._make_request(f"{self.base_url}/repos/{repo_name}")
        
        content = f"# {repo_info['name']}\n\n"
        content += f"**Repository:** {repo_info['full_name']}\n"
        content += f"**Description:** {repo_info.get('description', 'No description')}\n"
        content += f"**Language:** {repo_info.get('language', 'Not specified')}\n"
        content += f"**Stars:** {repo_info.get('stargazers_count', 0)}\n"
        content += f"**Forks:** {repo_info.get('forks_count', 0)}\n"
        content += f"**Created:** {repo_info.get('created_at', '')}\n"
        content += f"**Updated:** {repo_info.get('updated_at', '')}\n"
        content += f"**URL:** {repo_info.get('html_url', '')}\n\n"
        
        if repo_info.get('topics'):
            topics = ", ".join(repo_info['topics'])
            content += f"**Topics:** {topics}\n\n"
        
        # Try to get README
        try:
            readme_info = self._make_request(f"{self.base_url}/repos/{repo_name}/readme")
            if readme_info.get("encoding") == "base64":
                readme_content = base64.b64decode(readme_info["content"]).decode("utf-8")
                content += "## README\n\n" + readme_content
        except ValueError:
            content += "## README\n\nNo README file found."
        
        yield self.create_variable_message("content", content)
        yield self.create_variable_message("page_id", page_id)
        yield self.create_variable_message("title", repo_info['name'])
        yield self.create_variable_message("repository", repo_name)
        yield self.create_variable_message("type", "repository")
    
    def _get_file_content(self, page_id: str) -> Generator[DatasourceMessage, None, None]:
        """Get file content"""
        # page_id format: "file:owner/repo:path"
        parts = page_id.split(":", 2)
        repo_name = parts[1]
        file_path = parts[2]
        
        file_info = self._make_request(f"{self.base_url}/repos/{repo_name}/contents/{file_path}")
        
        if file_info.get("type") != "file":
            raise ValueError("Can only get content for files, not directories")
        
        # Get file content
        if file_info.get("encoding") == "base64":
            content = base64.b64decode(file_info["content"]).decode("utf-8")
        else:
            download_url = file_info.get("download_url")
            if download_url:
                response = requests.get(download_url, timeout=30)
                response.raise_for_status()
                content = response.text
            else:
                content = file_info.get("content", "")
        
        # If it's a Markdown file, add title
        file_name = file_info["name"]
        if file_name.lower().endswith(('.md', '.markdown')):
            content = f"# {file_name}\n\n{content}"
        
        yield self.create_variable_message("content", content)
        yield self.create_variable_message("page_id", page_id)
        yield self.create_variable_message("title", file_name)
        yield self.create_variable_message("repository", repo_name)
        yield self.create_variable_message("file_path", file_path)
        yield self.create_variable_message("type", "file")
    
    def _get_issue_content(self, page_id: str) -> Generator[DatasourceMessage, None, None]:
        """Get Issue content"""
        # page_id format: "issue:owner/repo:number"
        parts = page_id.split(":", 2)
        repo_name = parts[1]
        issue_number = parts[2]
        
        issue = self._make_request(f"{self.base_url}/repos/{repo_name}/issues/{issue_number}")
        
        content = f"# Issue #{issue['number']}: {issue['title']}\n\n"
        content += f"**Repository:** {repo_name}\n"
        content += f"**Author:** {issue['user']['login']}\n"
        content += f"**State:** {issue['state']}\n"
        content += f"**Created:** {issue['created_at']}\n"
        content += f"**Updated:** {issue['updated_at']}\n"
        content += f"**URL:** {issue['html_url']}\n\n"
        
        if issue.get('labels'):
            labels = ", ".join([label['name'] for label in issue['labels']])
            content += f"**Labels:** {labels}\n\n"
        
        if issue.get('body'):
            content += "## Description\n\n"
            content += issue['body'] + "\n\n"
        
        # Get comments
        try:
            comments = self._make_request(f"{self.base_url}/repos/{repo_name}/issues/{issue_number}/comments")
            if comments:
                content += "## Comments\n\n"
                for comment in comments:
                    content += f"### {comment['user']['login']} - {comment['created_at']}\n\n"
                    content += comment['body'] + "\n\n"
        except ValueError:
            pass
        
        yield self.create_variable_message("content", content)
        yield self.create_variable_message("page_id", page_id)
        yield self.create_variable_message("title", f"Issue #{issue['number']}: {issue['title']}")
        yield self.create_variable_message("repository", repo_name)
        yield self.create_variable_message("issue_number", issue_number)
        yield self.create_variable_message("type", "issue")
    
    def _get_pr_content(self, page_id: str) -> Generator[DatasourceMessage, None, None]:
        """Get PR content"""
        # page_id format: "pr:owner/repo:number"
        parts = page_id.split(":", 2)
        repo_name = parts[1]
        pr_number = parts[2]
        
        pr = self._make_request(f"{self.base_url}/repos/{repo_name}/pulls/{pr_number}")
        
        content = f"# Pull Request #{pr['number']}: {pr['title']}\n\n"
        content += f"**Repository:** {repo_name}\n"
        content += f"**Author:** {pr['user']['login']}\n"
        content += f"**State:** {pr['state']}\n"
        content += f"**Base Branch:** {pr['base']['ref']}\n"
        content += f"**Head Branch:** {pr['head']['ref']}\n"
        content += f"**Created:** {pr['created_at']}\n"
        content += f"**Updated:** {pr['updated_at']}\n"
        content += f"**URL:** {pr['html_url']}\n\n"
        
        if pr.get('body'):
            content += "## Description\n\n"
            content += pr['body'] + "\n\n"
        
        # Get comments
        try:
            comments = self._make_request(f"{self.base_url}/repos/{repo_name}/issues/{pr_number}/comments")
            if comments:
                content += "## Comments\n\n"
                for comment in comments:
                    content += f"### {comment['user']['login']} - {comment['created_at']}\n\n"
                    content += comment['body'] + "\n\n"
        except ValueError:
            pass
        
        yield self.create_variable_message("content", content)
        yield self.create_variable_message("page_id", page_id)
        yield self.create_variable_message("title", f"PR #{pr['number']}: {pr['title']}")
        yield self.create_variable_message("repository", repo_name)
        yield self.create_variable_message("pr_number", pr_number)
        yield self.create_variable_message("type", "pull_request")