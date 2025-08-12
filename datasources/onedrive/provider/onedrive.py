from typing import Any, Mapping

from dify_plugin.interfaces.datasource import DatasourceProvider, DatasourceOAuthCredentials
import requests
import urllib.parse
from flask import Request


class OneDriveDatasourceProvider(DatasourceProvider):
    _AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    _TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    _USERINFO_URL = "https://graph.microsoft.com/v1.0/me"

    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        pass

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        scopes = [
            "offline_access",
            "User.Read",
            "Files.Read",
            "Files.Read.All",
        ]
        params = {
            "client_id": system_credentials["client_id"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "response_mode": "query",
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> DatasourceOAuthCredentials:
        code = request.args.get("code")
        if not code:
            raise ValueError("No code provided")

        token_data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
            "scope": "offline_access User.Read Files.Read Files.Read.All",
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        token_response = requests.post(self._TOKEN_URL, data=token_data, headers=headers, timeout=15)
        if token_response.status_code >= 400:
            raise ValueError(f"Microsoft token endpoint error: {token_response.status_code} {token_response.text}")
        token_json = token_response.json()
        access_token = token_json.get("access_token")
        refresh_token = token_json.get("refresh_token")
        if not access_token:
            raise ValueError(f"Error in Microsoft OAuth token exchange: {token_json}")

        userinfo_headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        userinfo_resp = requests.get(self._USERINFO_URL, headers=userinfo_headers, timeout=10)
        user = userinfo_resp.json()

        return DatasourceOAuthCredentials(
            name=user.get("displayName") or user.get("userPrincipalName"),
            avatar_url=None,
            credentials={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "client_id": system_credentials["client_id"],
                "client_secret": system_credentials["client_secret"],
                "user_email": user.get("userPrincipalName"),
            },
        )

    def _refresh_access_token(self, credentials: Mapping[str, Any]) -> Mapping[str, Any]:
        """
        按照微软官方 OAuth 2.0 v2.0 标准刷新访问令牌
        文档: https://learn.microsoft.com/zh-cn/azure/active-directory/develop/v2-oauth2-auth-code-flow#refresh-the-access-token
        """
        refresh_token = credentials.get("refresh_token")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        
        if not refresh_token or not client_id or not client_secret:
            raise ValueError("Missing required credentials for token refresh")

        token_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "offline_access User.Read Files.Read Files.Read.All",
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        
        token_response = requests.post(self._TOKEN_URL, data=token_data, headers=headers, timeout=15)
        if token_response.status_code >= 400:
            raise ValueError(f"Microsoft token refresh error: {token_response.status_code} {token_response.text}")
        
        token_json = token_response.json()
        new_access_token = token_json.get("access_token")
        new_refresh_token = token_json.get("refresh_token")
        
        if not new_access_token:
            raise ValueError(f"Error in Microsoft token refresh: {token_json}")

        # 返回更新后的凭证
        updated_credentials = dict(credentials)
        updated_credentials["access_token"] = new_access_token
        if new_refresh_token:  # 微软可能返回新的 refresh_token
            updated_credentials["refresh_token"] = new_refresh_token
            
        return updated_credentials

