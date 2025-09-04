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
                "user_email": user.get("userPrincipalName"),
            },
        )

    def _refresh_access_token(self, credentials: Mapping[str, Any]) -> Mapping[str, Any]:
        """
        Refresh access token according to Microsoft OAuth 2.0 v2.0 standard
        Documentation: https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-auth-code-flow#refresh-the-access-token
        Note: client_secret must be obtained from system configuration
        """
        refresh_token = credentials.get("refresh_token")
        
        if not refresh_token:
            raise ValueError("Missing refresh_token for token refresh")

        # Note: This implementation requires system configuration access for client_secret
        # In a production implementation, you would need to access system_credentials here
        raise ValueError("Token refresh requires system configuration access. Please re-authorize through OAuth.")

