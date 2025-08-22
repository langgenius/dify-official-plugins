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


class GitLabDataSource(OnlineDocumentDatasource):
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # GitLab URL will be set from credentials, default to gitlab.com
        self.gitlab_url = None
        self.base_url = None
        
    def _get_headers(self) -> Dict[str, str]:
        """获取 API 请求头"""
        credentials = self.runtime.credentials
        access_token = credentials.get("access_token")
        
        return {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "Dify-GitLab-Datasource"
        }
    
    def _get_gitlab_url(self) -> str:
        """获取 GitLab URL"""
        if self.gitlab_url is None:
            credentials = self.runtime.credentials
            self.gitlab_url = credentials.get("gitlab_url", "https://gitlab.com").rstrip("/")
            self.base_url = f"{self.gitlab_url}/api/v4"
        return self.gitlab_url
    
    def _handle_rate_limit(self, response: requests.Response) -> None:
        """处理 API 限流"""
        if response.status_code == 429:
            # GitLab uses 429 for rate limiting
            retry_after = response.headers.get("Retry-After", "60")
            try:
                sleep_time = int(retry_after)
            except ValueError:
                sleep_time = 60
            raise ValueError(f"GitLab API rate limit exceeded. Please wait {sleep_time} seconds.")
        elif response.status_code == 401:
            raise ValueError("Invalid GitLab access token. Please check your credentials.")
        elif response.status_code == 403:
            raise ValueError("Access forbidden. Check your GitLab permissions.")
        elif response.status_code >= 400:
            raise ValueError(f"GitLab API error: {response.status_code} - {response.text}")
    
    def _make_request(self, url: str, params: Optional[Dict] = None) -> Dict:
        """发起 API 请求并处理错误"""
        # Ensure GitLab URL is set
        self._get_gitlab_url()
        headers = self._get_headers()
        response = requests.get(url, headers=headers, params=params, timeout=30)
        self._handle_rate_limit(response)
        return response.json()
    
    def _get_pages(self, datasource_parameters: dict[str, Any]) -> DatasourceGetPagesResponse:
        """获取 GitLab 页面列表（项目、Issues、MRs）"""
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            raise ValueError("Access token not found in credentials")
        
        # 确保设置了 GitLab URL
        self._get_gitlab_url()
        
        # 获取用户信息
        user_info = self._make_request(f"{self.base_url}/user")
        workspace_name = f"{user_info.get('name', user_info.get('username'))}'s GitLab"
        workspace_icon = user_info.get('avatar_url', '')
        workspace_id = str(user_info.get('id', ''))
        
        pages = []
        
        # 获取用户项目
        projects = self._get_projects()
        for project in projects:
            # 添加项目作为页面
            pages.append({
                "page_id": f"project:{project['path_with_namespace']}",
                "page_name": project['name'],
                "last_edited_time": project.get("last_activity_at", ""),
                "type": "project",
                "url": project['web_url'],
                "metadata": {
                    "description": project.get("description", ""),
                    "language": project.get("default_branch", ""),
                    "stars": project.get("star_count", 0),
                    "updated_at": project.get("last_activity_at", ""),
                    "private": not project.get("visibility", "private") == "public"
                }
            })
            
            # 添加 README 文件（如果存在）
            try:
                # GitLab API: GET /projects/:id/repository/files/:file_path
                project_id = project['id']
                readme_info = self._make_request(f"{self.base_url}/projects/{project_id}/repository/files/README.md")
                pages.append({
                    "page_id": f"file:{project['path_with_namespace']}:README.md",
                    "page_name": f"{project['name']} - README",
                    "last_edited_time": project.get("last_activity_at", ""),
                    "type": "file",
                    "url": f"{project['web_url']}/-/blob/{project.get('default_branch', 'main')}/README.md",
                    "metadata": {
                        "project": project['path_with_namespace'],
                        "file_path": "README.md",
                        "size": readme_info.get('size', 0)
                    }
                })
            except ValueError:
                pass  # README 不存在
            
            # 添加热门 Issues
            try:
                project_id = project['id']
                issues = self._make_request(
                    f"{self.base_url}/projects/{project_id}/issues",
                    params={"state": "all", "per_page": 5, "order_by": "updated_at"}
                )
                for issue in issues:
                    pages.append({
                        "page_id": f"issue:{project['path_with_namespace']}:{issue['iid']}",
                        "page_name": f"Issue #{issue['iid']}: {issue['title']}",
                        "last_edited_time": issue.get('updated_at', ''),
                        "type": "issue",
                        "url": issue['web_url'],
                        "metadata": {
                            "project": project['path_with_namespace'],
                            "issue_number": issue['iid'],
                            "state": issue['state'],
                            "author": issue['author']['username'],
                            "created_at": issue['created_at']
                        }
                    })
            except ValueError:
                pass  # Issues 访问失败
            
            # 添加热门 Merge Requests
            try:
                project_id = project['id']
                merge_requests = self._make_request(
                    f"{self.base_url}/projects/{project_id}/merge_requests",
                    params={"state": "all", "per_page": 5, "order_by": "updated_at"}
                )
                for mr in merge_requests:
                    pages.append({
                        "page_id": f"mr:{project['path_with_namespace']}:{mr['iid']}",
                        "page_name": f"MR #{mr['iid']}: {mr['title']}",
                        "last_edited_time": mr.get('updated_at', ''),
                        "type": "merge_request",
                        "url": mr['web_url'],
                        "metadata": {
                            "project": project['path_with_namespace'],
                            "mr_number": mr['iid'],
                            "state": mr['state'],
                            "author": mr['author']['username'],
                            "target_branch": mr['target_branch'],
                            "source_branch": mr['source_branch']
                        }
                    })
            except ValueError:
                pass  # MRs 访问失败
        
        online_document_info = OnlineDocumentInfo(
            workspace_name=workspace_name,
            workspace_icon=workspace_icon,
            workspace_id=workspace_id,
            pages=pages,
            total=len(pages),
        )
        
        return DatasourceGetPagesResponse(result=[online_document_info])
    
    def _get_projects(self, max_projects: int = 20) -> List[Dict]:
        """获取用户项目列表"""
        params = {
            "per_page": max_projects, 
            "order_by": "last_activity_at", 
            "sort": "desc",
            "membership": True  # 只获取用户有权限的项目
        }
        projects = self._make_request(f"{self.base_url}/projects", params)
        return projects
    
    def _get_content(self, page: GetOnlineDocumentPageContentRequest) -> Generator[DatasourceMessage, None, None]:
        """获取页面内容"""
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            raise ValueError("Access token not found in credentials")
        
        # 确保设置了 GitLab URL
        self._get_gitlab_url()
        
        page_id = page.page_id
        
        if page_id.startswith("project:"):
            # 获取项目信息
            yield from self._get_project_content(page_id)
        elif page_id.startswith("file:"):
            # 获取文件内容
            yield from self._get_file_content(page_id)
        elif page_id.startswith("issue:"):
            # 获取 Issue 内容
            yield from self._get_issue_content(page_id)
        elif page_id.startswith("mr:"):
            # 获取 MR 内容
            yield from self._get_mr_content(page_id)
        else:
            raise ValueError(f"Unsupported page type: {page_id}")
    
    def _get_project_content(self, page_id: str) -> Generator[DatasourceMessage, None, None]:
        """获取项目信息内容"""
        project_path = page_id[8:]  # 移除 "project:" 前缀
        
        # GitLab uses project path with namespace or project ID
        project_info = self._make_request(f"{self.base_url}/projects/{project_path.replace('/', '%2F')}")
        
        content = f"# {project_info['name']}\n\n"
        content += f"**Project:** {project_info['path_with_namespace']}\n"
        content += f"**Description:** {project_info.get('description', 'No description')}\n"
        content += f"**Default Branch:** {project_info.get('default_branch', 'main')}\n"
        content += f"**Stars:** {project_info.get('star_count', 0)}\n"
        content += f"**Forks:** {project_info.get('forks_count', 0)}\n"
        content += f"**Created:** {project_info.get('created_at', '')}\n"
        content += f"**Last Activity:** {project_info.get('last_activity_at', '')}\n"
        content += f"**URL:** {project_info.get('web_url', '')}\n\n"
        
        if project_info.get('topics'):
            topics = ", ".join(project_info['topics'])
            content += f"**Topics:** {topics}\n\n"
        
        # 尝试获取 README
        try:
            project_id = project_info['id']
            readme_info = self._make_request(f"{self.base_url}/projects/{project_id}/repository/files/README.md")
            if readme_info.get("encoding") == "base64":
                readme_content = base64.b64decode(readme_info["content"]).decode("utf-8")
                content += "## README\n\n" + readme_content
        except ValueError:
            content += "## README\n\nNo README file found."
        
        yield self.create_variable_message("content", content)
        yield self.create_variable_message("page_id", page_id)
        yield self.create_variable_message("title", project_info['name'])
        yield self.create_variable_message("project", project_path)
        yield self.create_variable_message("type", "project")
    
    def _get_file_content(self, page_id: str) -> Generator[DatasourceMessage, None, None]:
        """获取文件内容"""
        # page_id format: "file:namespace/project:path"
        parts = page_id.split(":", 2)
        project_path = parts[1]
        file_path = parts[2]
        
        # URL encode the project path for GitLab API
        encoded_project = project_path.replace('/', '%2F')
        encoded_file_path = file_path.replace('/', '%2F')
        
        file_info = self._make_request(f"{self.base_url}/projects/{encoded_project}/repository/files/{encoded_file_path}")
        
        # 获取文件内容
        if file_info.get("encoding") == "base64":
            content = base64.b64decode(file_info["content"]).decode("utf-8")
        else:
            content = file_info.get("content", "")
        
        # 如果是 Markdown 文件，添加标题
        file_name = file_path.split('/')[-1]  # 获取文件名
        if file_name.lower().endswith(('.md', '.markdown')):
            content = f"# {file_name}\n\n{content}"
        
        yield self.create_variable_message("content", content)
        yield self.create_variable_message("page_id", page_id)
        yield self.create_variable_message("title", file_name)
        yield self.create_variable_message("project", project_path)
        yield self.create_variable_message("file_path", file_path)
        yield self.create_variable_message("type", "file")
    
    def _get_issue_content(self, page_id: str) -> Generator[DatasourceMessage, None, None]:
        """获取 Issue 内容"""
        # page_id format: "issue:namespace/project:iid"
        parts = page_id.split(":", 2)
        project_path = parts[1]
        issue_iid = parts[2]
        
        # URL encode the project path for GitLab API
        encoded_project = project_path.replace('/', '%2F')
        
        issue = self._make_request(f"{self.base_url}/projects/{encoded_project}/issues/{issue_iid}")
        
        content = f"# Issue #{issue['iid']}: {issue['title']}\n\n"
        content += f"**Project:** {project_path}\n"
        content += f"**Author:** {issue['author']['username']}\n"
        content += f"**State:** {issue['state']}\n"
        content += f"**Created:** {issue['created_at']}\n"
        content += f"**Updated:** {issue['updated_at']}\n"
        content += f"**URL:** {issue['web_url']}\n\n"
        
        if issue.get('labels'):
            labels = ", ".join(issue['labels'])
            content += f"**Labels:** {labels}\n\n"
        
        if issue.get('description'):
            content += "## Description\n\n"
            content += issue['description'] + "\n\n"
        
        # 获取评论 (notes)
        try:
            comments = self._make_request(f"{self.base_url}/projects/{encoded_project}/issues/{issue_iid}/notes")
            if comments:
                content += "## Comments\n\n"
                for comment in comments:
                    if not comment.get('system', False):  # 排除系统消息
                        content += f"### {comment['author']['username']} - {comment['created_at']}\n\n"
                        content += comment['body'] + "\n\n"
        except ValueError:
            pass
        
        yield self.create_variable_message("content", content)
        yield self.create_variable_message("page_id", page_id)
        yield self.create_variable_message("title", f"Issue #{issue['iid']}: {issue['title']}")
        yield self.create_variable_message("project", project_path)
        yield self.create_variable_message("issue_number", issue_iid)
        yield self.create_variable_message("type", "issue")
    
    def _get_mr_content(self, page_id: str) -> Generator[DatasourceMessage, None, None]:
        """获取 MR 内容"""
        # page_id format: "mr:namespace/project:iid"
        parts = page_id.split(":", 2)
        project_path = parts[1]
        mr_iid = parts[2]
        
        # URL encode the project path for GitLab API
        encoded_project = project_path.replace('/', '%2F')
        
        mr = self._make_request(f"{self.base_url}/projects/{encoded_project}/merge_requests/{mr_iid}")
        
        content = f"# Merge Request #{mr['iid']}: {mr['title']}\n\n"
        content += f"**Project:** {project_path}\n"
        content += f"**Author:** {mr['author']['username']}\n"
        content += f"**State:** {mr['state']}\n"
        content += f"**Target Branch:** {mr['target_branch']}\n"
        content += f"**Source Branch:** {mr['source_branch']}\n"
        content += f"**Created:** {mr['created_at']}\n"
        content += f"**Updated:** {mr['updated_at']}\n"
        content += f"**URL:** {mr['web_url']}\n\n"
        
        if mr.get('description'):
            content += "## Description\n\n"
            content += mr['description'] + "\n\n"
        
        # 获取评论 (notes)
        try:
            comments = self._make_request(f"{self.base_url}/projects/{encoded_project}/merge_requests/{mr_iid}/notes")
            if comments:
                content += "## Comments\n\n"
                for comment in comments:
                    if not comment.get('system', False):  # 排除系统消息
                        content += f"### {comment['author']['username']} - {comment['created_at']}\n\n"
                        content += comment['body'] + "\n\n"
        except ValueError:
            pass
        
        yield self.create_variable_message("content", content)
        yield self.create_variable_message("page_id", page_id)
        yield self.create_variable_message("title", f"MR #{mr['iid']}: {mr['title']}")
        yield self.create_variable_message("project", project_path)
        yield self.create_variable_message("mr_number", mr_iid)
        yield self.create_variable_message("type", "merge_request")