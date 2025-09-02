from typing import Any, Mapping
import requests
import urllib.parse
from flask import Request
import msal

from dify_plugin.interfaces.datasource import DatasourceProvider, DatasourceOAuthCredentials


class MicrosoftTeamsDatasourceProvider(DatasourceProvider):
    _AUTH_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
    _TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    _USERINFO_URL = "https://graph.microsoft.com/v1.0/me"

    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        """验证凭证有效性"""
        access_token = credentials.get("access_token")
        if not access_token:
            raise ValueError("Access token is required")
        
        # 验证 token 有效性
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        try:
            response = requests.get(self._USERINFO_URL, headers=headers, timeout=10)
            if response.status_code == 401:
                raise ValueError("Invalid access token")
            elif response.status_code >= 400:
                raise ValueError(f"Microsoft Graph API error: {response.status_code} {response.text}")
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Failed to validate Microsoft Teams token: {str(e)}")

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        """获取 OAuth 授权 URL"""
        tenant_id = system_credentials.get("tenant_id", "common")
        
        scopes = [
            "https://graph.microsoft.com/Team.ReadBasic.All",      # 读取团队基本信息
            "https://graph.microsoft.com/Channel.ReadBasic.All",   # 读取频道基本信息  
            "https://graph.microsoft.com/ChannelMessage.Read.All", # 读取频道消息
            "https://graph.microsoft.com/Chat.Read",               # 读取聊天消息
            "https://graph.microsoft.com/Files.Read.All",          # 读取文件
            "https://graph.microsoft.com/User.Read",               # 读取用户信息
            "offline_access"                                       # 获取刷新令牌
        ]
        
        params = {
            "client_id": system_credentials["client_id"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "response_mode": "query",
        }
        
        auth_url = self._AUTH_URL.format(tenant_id=tenant_id)
        return f"{auth_url}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> DatasourceOAuthCredentials:
        """处理 OAuth 回调并获取凭证"""
        code = request.args.get("code")
        if not code:
            raise ValueError("No authorization code provided")

        tenant_id = system_credentials.get("tenant_id", "common")
        
        # 使用 MSAL 交换 access token
        app = msal.ConfidentialClientApplication(
            system_credentials["client_id"],
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=system_credentials["client_secret"]
        )
        
        scopes = [
            "https://graph.microsoft.com/Team.ReadBasic.All",
            "https://graph.microsoft.com/Channel.ReadBasic.All",
            "https://graph.microsoft.com/ChannelMessage.Read.All",
            "https://graph.microsoft.com/Chat.Read",
            "https://graph.microsoft.com/Files.Read.All",
            "https://graph.microsoft.com/User.Read"
        ]
        
        try:
            result = app.acquire_token_by_authorization_code(
                code,
                scopes=scopes,
                redirect_uri=redirect_uri
            )
            
            if "error" in result:
                raise ValueError(f"Microsoft OAuth error: {result.get('error_description', result['error'])}")
            
            access_token = result.get("access_token")
            refresh_token = result.get("refresh_token")
            
            if not access_token:
                raise ValueError("Failed to get access token from Microsoft")
            
        except Exception as e:
            raise ValueError(f"Microsoft OAuth token exchange failed: {str(e)}")

        # 获取用户信息
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        try:
            userinfo_resp = requests.get(self._USERINFO_URL, headers=headers, timeout=10)
            if userinfo_resp.status_code >= 400:
                raise ValueError(f"Failed to get user info: {userinfo_resp.status_code}")
            
            user = userinfo_resp.json()
        except Exception as e:
            raise ValueError(f"Failed to retrieve user information: {str(e)}")

        return DatasourceOAuthCredentials(
            name=user.get("displayName") or user.get("userPrincipalName"),
            avatar_url=None,  # Microsoft Graph 不直接提供头像 URL
            credentials={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "client_id": system_credentials["client_id"],
                "client_secret": system_credentials["client_secret"],
                "tenant_id": tenant_id,
                "user_id": user.get("id"),
            },
        )

    def _refresh_access_token(self, credentials: Mapping[str, Any]) -> Mapping[str, Any]:
        """刷新访问令牌"""
        refresh_token = credentials.get("refresh_token")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        tenant_id = credentials.get("tenant_id", "common")
        
        if not all([refresh_token, client_id, client_secret]):
            raise ValueError("Missing required credentials for token refresh")

        # 使用 MSAL 刷新令牌
        app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret
        )
        
        scopes = [
            "https://graph.microsoft.com/Team.ReadBasic.All",
            "https://graph.microsoft.com/Channel.ReadBasic.All", 
            "https://graph.microsoft.com/ChannelMessage.Read.All",
            "https://graph.microsoft.com/Chat.Read",
            "https://graph.microsoft.com/Files.Read.All",
            "https://graph.microsoft.com/User.Read"
        ]
        
        try:
            result = app.acquire_token_by_refresh_token(refresh_token, scopes=scopes)
            
            if "error" in result:
                raise ValueError(f"Token refresh error: {result.get('error_description', result['error'])}")
            
            new_access_token = result.get("access_token")
            new_refresh_token = result.get("refresh_token", refresh_token)  # 使用新的或保持原有的
            
            if not new_access_token:
                raise ValueError("Failed to refresh access token")
            
            # 返回更新后的凭证
            updated_credentials = dict(credentials)
            updated_credentials["access_token"] = new_access_token
            updated_credentials["refresh_token"] = new_refresh_token
            
            return updated_credentials
            
        except Exception as e:
            raise ValueError(f"Failed to refresh Microsoft Teams token: {str(e)}")



