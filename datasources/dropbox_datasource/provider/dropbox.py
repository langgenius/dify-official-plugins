import secrets
import time
import urllib.parse
from typing import Any, Mapping

import requests
import dropbox
from dropbox.exceptions import AuthError, ApiError
from werkzeug import Request

from dify_plugin.interfaces.datasource import DatasourceProvider, DatasourceOAuthCredentials
from dify_plugin.errors.tool import ToolProviderCredentialValidationError, DatasourceOAuthError


class DropboxDatasourceProvider(DatasourceProvider):
    _AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
    _TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"

    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        try:
            # Check if access_token is provided in credentials
            if "access_token" not in credentials or not credentials.get("access_token"):
                raise ToolProviderCredentialValidationError("Dropbox access token is required.")
            
            access_token = credentials.get("access_token")
            
            # Try to authenticate with Dropbox using the access token
            try:
                dbx = dropbox.Dropbox(access_token)
                # Verify the connection by getting current account
                dbx.users_get_current_account()
            except AuthError as e:
                raise ToolProviderCredentialValidationError(f"Invalid Dropbox access token: {str(e)}")
            except Exception as e:
                raise ToolProviderCredentialValidationError(f"Failed to connect to Dropbox: {str(e)}")
                
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        """
        Generate the authorization URL for the Dropbox OAuth 2.0 flow.
        """
        state = secrets.token_urlsafe(16)
        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "token_access_type": "offline",
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> DatasourceOAuthCredentials:
        """
        Exchange authorization code for access_token.
        """
        code = request.args.get("code")
        if not code:
            raise DatasourceOAuthError("No authorization code provided")

        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        try:
            response = requests.post(self._TOKEN_URL, data=data, headers=headers, timeout=30)
            response.raise_for_status()
            response_json = response.json()
            
            access_token = response_json.get("access_token")
            if not access_token:
                raise DatasourceOAuthError(f"Error in Dropbox OAuth: {response_json}")

            # Get user information
            try:
                dbx = dropbox.Dropbox(access_token)
                account_info = dbx.users_get_current_account()
                user_name = account_info.name.display_name
                user_email = account_info.email
                user_avatar = account_info.profile_photo_url if hasattr(account_info, 'profile_photo_url') else None
            except Exception as e:
                # If we can't get user info, use defaults
                user_name = "Dropbox User"
                user_email = None
                user_avatar = None

            return DatasourceOAuthCredentials(
                name=user_name or user_email or "Dropbox User",
                avatar_url=user_avatar,
                credentials={"access_token": access_token, "refresh_token": response_json.get("refresh_token", "")},
                expires_at=int(time.time()) + int(response_json["expires_in"]) if response_json.get("expires_in") else -1
            )
            
        except requests.RequestException as e:
            raise DatasourceOAuthError(f"Failed to exchange code for token: {str(e)}")
        except Exception as e:
            raise DatasourceOAuthError(f"Unexpected error during OAuth: {str(e)}")

    def _oauth_refresh_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    ) -> DatasourceOAuthCredentials:
        """Exchange the stored refresh token for a new short-lived access token."""
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise DatasourceOAuthError("No refresh token available. Please re-authorize.")
        try:
            response = requests.post(
                self._TOKEN_URL,
                data={"grant_type": "refresh_token", "refresh_token": refresh_token,
                      "client_id": system_credentials["client_id"],
                      "client_secret": system_credentials["client_secret"]},
                timeout=30,
            )
            response.raise_for_status()
            token = response.json()
            access_token = token.get("access_token")
            if not access_token:
                raise DatasourceOAuthError("Dropbox returned no access token")
            account = dropbox.Dropbox(access_token).users_get_current_account()
            return DatasourceOAuthCredentials(
                name=account.name.display_name or account.email or "Dropbox User",
                avatar_url=getattr(account, "profile_photo_url", None),
                credentials={"access_token": access_token, "refresh_token": refresh_token},
                expires_at=int(time.time()) + int(token["expires_in"]),
            )
        except Exception as e:
            raise DatasourceOAuthError(f"Failed to refresh Dropbox token: {str(e)}") from e
