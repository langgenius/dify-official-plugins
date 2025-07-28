import time
from typing import Any, Mapping
import requests
import secrets
import urllib.parse

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.entities.oauth import ToolOAuthCredentials


class OutlookProvider(ToolProvider):
    _SCOPE = "Mail.Read Mail.Send Mail.ReadWrite offline_access"

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """Validate access token by calling Microsoft Graph API."""
        if not credentials.get("access_token"):
            raise ToolProviderCredentialValidationError("Microsoft Graph access token is required.")
        
        headers = {"Authorization": f"Bearer {credentials['access_token']}"}
        response = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers, timeout=30)
        
        if response.status_code != 200:
            raise ToolProviderCredentialValidationError("Invalid or expired access token.")

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        """Generate OAuth authorization URL."""
        tenant_id = system_credentials.get("tenant_id", "common")
        auth_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
        
        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "scope": system_credentials.get("scope", self._SCOPE),
            "response_type": "code",
            "state": secrets.token_urlsafe(16)
        }
        return f"{auth_url}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Any
    ) -> ToolOAuthCredentials:
        """Exchange authorization code for access token."""
        # Get authorization code
        code = request.args.get("code")
        if not code:
            raise ToolProviderCredentialValidationError("No authorization code provided")
        
        # Exchange code for token
        tenant_id = system_credentials.get("tenant_id", "common")
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        
        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }
        
        response = requests.post(token_url, data=data, timeout=30)
        if response.status_code != 200:
            raise ToolProviderCredentialValidationError(f"Token exchange failed: {response.text}")
        
        token_data = response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")

        if not access_token or not refresh_token:
            raise ToolProviderCredentialValidationError("No access token or refresh token in response")
        
        return ToolOAuthCredentials(
            credentials={"access_token": access_token, "refresh_token": refresh_token},
            expires_at= token_data.get("expires_in", 3599) + int(time.time())
        )

    def oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> ToolOAuthCredentials:

        """Refresh OAuth credentials."""
        tenant_id = system_credentials.get("tenant_id", "common")
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "refresh_token": credentials.get("refresh_token"),
            "redirect_uri": redirect_uri,
            "grant_type": "refresh_token"
        }
        
        response = requests.post(token_url, data=data, timeout=30)
        if response.status_code != 200:
            raise ToolProviderCredentialValidationError(f"Token exchange failed: {response.text}")
        
        token_data = response.json()

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")

        if not access_token or not refresh_token:
            raise ToolProviderCredentialValidationError("No access token or refresh token in response")

        return ToolOAuthCredentials(
            credentials={"access_token": access_token, "refresh_token": refresh_token},
            expires_at= token_data.get("expires_in", 3599) + int(time.time())
        )