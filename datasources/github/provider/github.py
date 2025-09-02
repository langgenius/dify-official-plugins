from typing import Any, Mapping
import requests
import urllib.parse
from flask import Request

from dify_plugin.interfaces.datasource import DatasourceProvider, DatasourceOAuthCredentials


class GitHubDatasourceProvider(DatasourceProvider):
    _AUTH_URL = "https://github.com/login/oauth/authorize"
    _TOKEN_URL = "https://github.com/login/oauth/access_token"
    _USERINFO_URL = "https://api.github.com/user"

    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        """Validate credentials"""
        access_token = credentials.get("access_token")
        if not access_token:
            raise ValueError("Access token is required")
        
        # Validate token validity
        headers = {
            "Authorization": f"token {access_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Dify-GitHub-Datasource"
        }
        
        try:
            response = requests.get(self._USERINFO_URL, headers=headers, timeout=10)
            if response.status_code == 401:
                raise ValueError("Invalid access token")
            elif response.status_code >= 400:
                raise ValueError(f"GitHub API error: {response.status_code} {response.text}")
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Failed to validate GitHub token: {str(e)}")

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        """Get OAuth authorization URL"""
        scopes = [
            "repo",  # Access private and public repositories
            "user:email",  # Get user email
            "read:user",  # Read user information
        ]
        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "response_type": "code",
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> DatasourceOAuthCredentials:
        """Handle OAuth callback and get credentials"""
        code = request.args.get("code")
        if not code:
            raise ValueError("No authorization code provided")

        # Exchange access token
        token_data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
        }
        headers = {
            "Accept": "application/json",
            "User-Agent": "Dify-GitHub-Datasource"
        }
        
        token_response = requests.post(self._TOKEN_URL, data=token_data, headers=headers, timeout=15)
        if token_response.status_code >= 400:
            raise ValueError(f"GitHub token exchange error: {token_response.status_code} {token_response.text}")
        
        token_json = token_response.json()
        access_token = token_json.get("access_token")
        if not access_token:
            raise ValueError(f"Error in GitHub OAuth token exchange: {token_json}")

        # Get user information
        userinfo_headers = {
            "Authorization": f"token {access_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Dify-GitHub-Datasource"
        }
        userinfo_resp = requests.get(self._USERINFO_URL, headers=userinfo_headers, timeout=10)
        if userinfo_resp.status_code >= 400:
            raise ValueError(f"Failed to get GitHub user info: {userinfo_resp.status_code}")
        
        user = userinfo_resp.json()

        return DatasourceOAuthCredentials(
            name=user.get("name") or user.get("login"),
            avatar_url=user.get("avatar_url"),
            credentials={
                "access_token": access_token,
                "user_login": user.get("login"),
            },
        )

    def _refresh_access_token(self, credentials: Mapping[str, Any]) -> Mapping[str, Any]:
        """Refresh access token - GitHub doesn't support refresh token, return original credentials"""
        # GitHub OAuth tokens don't expire, no need to refresh
        # If token is invalid, re-authorization is required
        return credentials
