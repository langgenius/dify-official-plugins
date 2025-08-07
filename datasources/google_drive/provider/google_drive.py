import json
from typing import Any, Mapping

from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.interfaces.datasource import DatasourceProvider, DatasourceOAuthCredentials
from google.oauth2.credentials import Credentials
import requests
import urllib.parse
from flask import Request

class GoogleDriveDatasourceProvider(DatasourceProvider):

    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        pass
    
    _AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN_URL = "https://oauth2.googleapis.com/token"
    _USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        """
        Google OAuth URL
        """
        scopes = [
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/userinfo.email"
        ]
        params = {
            "client_id": system_credentials["client_id"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            # 'access_type': 'offline' will return a refresh_token, for long-term access
            "access_type": "offline",
            # 'prompt': 'consent' will force to display the authorization page every time, for debugging
            "prompt": "consent",
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> DatasourceOAuthCredentials:
        """
        Use the authorization code (code) to get the access token and user information.
        """
        code = request.args.get("code")
        if not code:
            raise ValueError("No code provided")

        # Step 1: Use code to exchange access_token and refresh_token
        token_data = {
            "code": code,
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        headers = {"Accept": "application/json"}
        token_response = requests.post(self._TOKEN_URL, data=token_data, headers=headers, timeout=10)
        token_response_json = token_response.json()

        access_token = token_response_json.get("access_token")
        refresh_token = token_response_json.get("refresh_token")

        if not access_token:
            raise ValueError(f"Error in Google OAuth token exchange: {token_response_json}")

        # Step 2: Use access_token to get user information
        userinfo_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        userinfo_response = requests.get(self._USERINFO_URL, headers=userinfo_headers, timeout=10)
        userinfo_json = userinfo_response.json()

        user_name = userinfo_json.get("name")
        user_picture = userinfo_json.get("picture")
        user_email = userinfo_json.get("email")

        # Return an object containing credentials and user information
        return DatasourceOAuthCredentials(
            name=user_name or user_email, # If no name, use email as backup
            avatar_url=user_picture,
            credentials={
                "access_token": access_token,
                "refresh_token": refresh_token,
                # Save client_id and client_secret for subsequent token refresh
                "client_id": system_credentials["client_id"],
                "client_secret": system_credentials["client_secret"],
                "user_email": user_email,
            },
        )

