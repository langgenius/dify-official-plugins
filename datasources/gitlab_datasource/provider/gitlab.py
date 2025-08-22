from typing import Any, Mapping
import requests
import urllib.parse
from flask import Request

from dify_plugin.interfaces.datasource import DatasourceProvider, DatasourceOAuthCredentials


class GitLabDatasourceProvider(DatasourceProvider):
    _AUTH_URL_TEMPLATE = "{gitlab_url}/oauth/authorize"
    _TOKEN_URL_TEMPLATE = "{gitlab_url}/oauth/token"
    _USERINFO_URL_TEMPLATE = "{gitlab_url}/api/v4/user"

    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        """验证凭证有效性"""
        access_token = credentials.get("access_token")
        gitlab_url = credentials.get("gitlab_url", "https://gitlab.com").rstrip("/")
        
        if not access_token:
            raise ValueError("Access token is required")
        
        # 验证 token 有效性
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "Dify-GitLab-Datasource"
        }
        
        user_url = self._USERINFO_URL_TEMPLATE.format(gitlab_url=gitlab_url)
        
        try:
            response = requests.get(user_url, headers=headers, timeout=10)
            if response.status_code == 401:
                raise ValueError("Invalid access token")
            elif response.status_code >= 400:
                raise ValueError(f"GitLab API error: {response.status_code} {response.text}")
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Failed to validate GitLab token: {str(e)}")

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        """获取 OAuth 授权 URL"""
        gitlab_url = system_credentials.get("gitlab_url", "https://gitlab.com").rstrip("/")
        
        # GitLab scopes
        scopes = [
            "read_user",  # 读取用户信息
            "read_repository",  # 读取仓库
            "api",  # 访问 API (包括项目、Issues、MR等)
        ]
        
        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "response_type": "code",
        }
        
        auth_url = self._AUTH_URL_TEMPLATE.format(gitlab_url=gitlab_url)
        return f"{auth_url}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> DatasourceOAuthCredentials:
        """处理 OAuth 回调并获取凭证"""
        code = request.args.get("code")
        if not code:
            raise ValueError("No authorization code provided")

        gitlab_url = system_credentials.get("gitlab_url", "https://gitlab.com").rstrip("/")

        # 交换 access token
        token_data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        headers = {
            "Accept": "application/json",
            "User-Agent": "Dify-GitLab-Datasource"
        }
        
        token_url = self._TOKEN_URL_TEMPLATE.format(gitlab_url=gitlab_url)
        token_response = requests.post(token_url, data=token_data, headers=headers, timeout=15)
        if token_response.status_code >= 400:
            raise ValueError(f"GitLab token exchange error: {token_response.status_code} {token_response.text}")
        
        token_json = token_response.json()
        access_token = token_json.get("access_token")
        if not access_token:
            raise ValueError(f"Error in GitLab OAuth token exchange: {token_json}")

        # 获取用户信息
        userinfo_headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "Dify-GitLab-Datasource"
        }
        user_url = self._USERINFO_URL_TEMPLATE.format(gitlab_url=gitlab_url)
        userinfo_resp = requests.get(user_url, headers=userinfo_headers, timeout=10)
        if userinfo_resp.status_code >= 400:
            raise ValueError(f"Failed to get GitLab user info: {userinfo_resp.status_code}")
        
        user = userinfo_resp.json()

        return DatasourceOAuthCredentials(
            name=user.get("name") or user.get("username"),
            avatar_url=user.get("avatar_url"),
            credentials={
                "access_token": access_token,
                "gitlab_url": gitlab_url,
                "client_id": system_credentials["client_id"],
                "client_secret": system_credentials["client_secret"],
                "user_login": user.get("username"),
            },
        )

    def _refresh_access_token(self, credentials: Mapping[str, Any]) -> Mapping[str, Any]:
        """刷新访问令牌 - GitLab 不支持 refresh token，返回原凭证"""
        # GitLab 的 OAuth token 默认不会过期，无需刷新
        # 如果 token 失效，需要重新授权
        return credentials
