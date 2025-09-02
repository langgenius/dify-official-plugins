from typing import Any, Mapping
import requests
import urllib.parse
import time
import certifi
from flask import Request
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from dify_plugin.interfaces.datasource import DatasourceProvider, DatasourceOAuthCredentials
from dify_plugin.errors.tool import ToolProviderCredentialValidationError, DatasourceOAuthError


class GitLabDatasourceProvider(DatasourceProvider):
    _AUTH_URL_TEMPLATE = "{gitlab_url}/oauth/authorize"
    _TOKEN_URL_TEMPLATE = "{gitlab_url}/oauth/token"
    _USERINFO_URL_TEMPLATE = "{gitlab_url}/api/v4/user"

    def _get_requests_session(self) -> requests.Session:
        """Create a requests session with retry strategy and SSL verification"""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.verify = certifi.where()
        return session

    def _safe_json_response(self, response: requests.Response) -> dict:
        """Safely parse JSON response with validation"""
        if response.status_code >= 400:
            raise DatasourceOAuthError(f"GitLab API error: {response.status_code} - {response.text}")
        
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise DatasourceOAuthError(f"Invalid response format: expected dict, got {type(data)}")
            return data
        except ValueError as e:
            raise DatasourceOAuthError(f"Invalid JSON response: {str(e)}")

    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        """验证凭证有效性"""
        access_token = credentials.get("access_token")
        gitlab_url = credentials.get("gitlab_url", "https://gitlab.com").rstrip("/")
        
        if not access_token:
            raise ToolProviderCredentialValidationError("Access token is required")
        
        # Validate access token format
        if not isinstance(access_token, str) or len(access_token.strip()) == 0:
            raise ToolProviderCredentialValidationError("Invalid access token format")
        
        # Validate GitLab URL format
        if not isinstance(gitlab_url, str) or not gitlab_url.startswith(("http://", "https://")):
            raise ToolProviderCredentialValidationError(f"Invalid GitLab URL format: {gitlab_url}")
        
        # 验证 token 有效性
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "Dify-GitLab-Datasource"
        }
        
        user_url = self._USERINFO_URL_TEMPLATE.format(gitlab_url=gitlab_url)
        
        try:
            session = self._get_requests_session()
            response = session.get(user_url, headers=headers, timeout=10)
            if response.status_code == 401:
                raise ToolProviderCredentialValidationError("Invalid access token")
            elif response.status_code >= 400:
                raise ToolProviderCredentialValidationError(f"GitLab API error: {response.status_code} {response.text}")
        except requests.exceptions.RequestException as e:
            raise ToolProviderCredentialValidationError(f"Failed to validate GitLab token: {str(e)}")

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
        session = self._get_requests_session()
        
        try:
            token_response = session.post(token_url, data=token_data, headers=headers, timeout=15)
            token_json = self._safe_json_response(token_response)
            
            access_token = token_json.get("access_token")
            refresh_token = token_json.get("refresh_token")
            expires_in = token_json.get("expires_in", 7200)  # GitLab default is 2 hours
            expires_at = int(time.time()) + expires_in
            
            if not access_token:
                raise DatasourceOAuthError(f"Error in GitLab OAuth token exchange: missing access_token")
        except requests.RequestException as e:
            raise DatasourceOAuthError(f"Failed to exchange code for token: {str(e)}")

        # 获取用户信息
        userinfo_headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "Dify-GitLab-Datasource"
        }
        user_url = self._USERINFO_URL_TEMPLATE.format(gitlab_url=gitlab_url)
        try:
            userinfo_resp = session.get(user_url, headers=userinfo_headers, timeout=10)
            user = self._safe_json_response(userinfo_resp)
        except requests.RequestException as e:
            raise DatasourceOAuthError(f"Failed to get user information: {str(e)}")

        return DatasourceOAuthCredentials(
            name=user.get("name") or user.get("username"),
            avatar_url=user.get("avatar_url"),
            expires_at=expires_at,
            credentials={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "gitlab_url": gitlab_url,
                "user_login": user.get("username"),
                "token_type": token_json.get("token_type", "bearer"),
            },
        )

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> DatasourceOAuthCredentials:
        """
        Refresh the access token using refresh token.
        
        Args:
            redirect_uri: The redirect URI
            system_credentials: System credentials containing client_id and client_secret
            credentials: Current credentials containing refresh_token
            
        Returns:
            DatasourceOAuthCredentials object with new access token
        """
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise DatasourceOAuthError("Refresh token not available. Please re-authorize.")

        gitlab_url = credentials.get("gitlab_url", "https://gitlab.com").rstrip("/")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
        }
        
        headers = {
            "Accept": "application/json",
            "User-Agent": "Dify-GitLab-Datasource"
        }
        
        token_url = self._TOKEN_URL_TEMPLATE.format(gitlab_url=gitlab_url)
        session = self._get_requests_session()
        
        try:
            response = session.post(token_url, data=data, headers=headers, timeout=30)
            response_data = self._safe_json_response(response)
            
            access_token = response_data.get("access_token")
            new_refresh_token = response_data.get("refresh_token", refresh_token)
            expires_in = response_data.get("expires_in", 7200)
            expires_at = int(time.time()) + expires_in
            
            if not access_token:
                raise DatasourceOAuthError(f"Failed to refresh access token: missing access_token")

            # Get user information
            userinfo_headers = {
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "Dify-GitLab-Datasource"
            }

            try:
                user_url = self._USERINFO_URL_TEMPLATE.format(gitlab_url=gitlab_url)
                userinfo_response = session.get(user_url, headers=userinfo_headers, timeout=30)
                user = self._safe_json_response(userinfo_response)
            except requests.RequestException as e:
                raise DatasourceOAuthError(f"Failed to get user information: {str(e)}")

            updated_credentials = {
                "access_token": access_token,
                "refresh_token": new_refresh_token,
                "gitlab_url": gitlab_url,
                "user_login": user.get("username"),
                "token_type": response_data.get("token_type", "bearer"),
            }
                
            return DatasourceOAuthCredentials(
                name=user.get("name") or user.get("username"),
                avatar_url=user.get("avatar_url"),
                expires_at=expires_at,
                credentials=updated_credentials,
            )
            
        except requests.exceptions.SSLError as e:
            raise DatasourceOAuthError(
                f"SSL error when refreshing token. This might be due to network proxy or firewall settings: {str(e)}"
            )
        except requests.exceptions.ConnectionError as e:
            raise DatasourceOAuthError(
                f"Connection error when refreshing token. Please check your network connection: {str(e)}"
            )
        except requests.exceptions.Timeout as e:
            raise DatasourceOAuthError(
                f"Timeout when refreshing token. The GitLab OAuth server might be slow or unreachable: {str(e)}"
            )
        except requests.RequestException as e:
            raise DatasourceOAuthError(f"Failed to refresh token: {str(e)}")

    def _refresh_access_token(self, credentials: Mapping[str, Any]) -> Mapping[str, Any]:
        """Legacy method for backward compatibility - delegates to OAuth refresh"""
        # This method is kept for backward compatibility
        # The actual refresh logic is now in _oauth_refresh_credentials
        return credentials
