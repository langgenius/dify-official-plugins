import secrets
import urllib.parse
from collections.abc import Mapping
from typing import Any

import requests
from dify_plugin import ToolProvider
from dify_plugin.entities.oauth import ToolOAuthCredentials
from dify_plugin.errors.tool import (
    ToolProviderCredentialValidationError,
    ToolProviderOAuthError,
)
from werkzeug import Request


class GoogleCalendarProvider(ToolProvider):
    _AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN_URL = "https://oauth2.googleapis.com/token"
    _REFRESH_URL = "https://oauth2.googleapis.com/token"
    _API_BASE_URL = "https://www.googleapis.com/calendar/v3"

    # Built-in OAuth scope for Google Calendar - provides full calendar access
    _OAUTH_SCOPE = "https://www.googleapis.com/auth/calendar"

    def _oauth_get_authorization_url(
        self, redirect_uri: str, system_credentials: Mapping[str, Any]
    ) -> str:
        """
        Generate the authorization URL for the Google Calendar OAuth.
        """
        state = secrets.token_urlsafe(16)
        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "scope": self._OAUTH_SCOPE,  # Use built-in scope
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> ToolOAuthCredentials:
        """
        Exchange authorization code for access_token and refresh_token.
        """
        code = request.args.get("code")
        if not code:
            raise ToolProviderOAuthError("No authorization code provided")

        error = request.args.get("error")
        if error:
            raise ToolProviderOAuthError(f"OAuth error: {error}")

        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }

        try:
            response = requests.post(self._TOKEN_URL, data=data, timeout=10)
            response.raise_for_status()
            token_data = response.json()
        except requests.RequestException as e:
            raise ToolProviderOAuthError(f"Failed to exchange code for token: {str(e)}")

        if "access_token" not in token_data:
            raise ToolProviderOAuthError(f"No access token in response: {token_data}")

        # Calculate expiration time
        expires_at = -1  # Default to never expire
        if "expires_in" in token_data:
            import time

            expires_at = int(time.time()) + int(token_data["expires_in"])

        credentials = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "token_type": token_data.get("token_type", "Bearer"),
        }

        return ToolOAuthCredentials(credentials=credentials, expires_at=expires_at)

    def _oauth_refresh_credentials(
        self,
        redirect_uri: str,
        system_credentials: Mapping[str, Any],
        credentials: Mapping[str, Any],
    ) -> ToolOAuthCredentials:
        """
        Refresh the access token using refresh token.
        """
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise ToolProviderOAuthError("No refresh token available")

        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            response = requests.post(self._REFRESH_URL, data=data, timeout=10)
            response.raise_for_status()
            token_data = response.json()
        except requests.RequestException as e:
            raise ToolProviderOAuthError(f"Failed to refresh token: {str(e)}")

        if "access_token" not in token_data:
            raise ToolProviderOAuthError(
                f"No access token in refresh response: {token_data}"
            )

        # Calculate expiration time
        expires_at = -1  # Default to never expire
        if "expires_in" in token_data:
            import time

            expires_at = int(time.time()) + int(token_data["expires_in"])

        # Update credentials, keep existing refresh_token if new one not provided
        new_credentials = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token", refresh_token),
            "token_type": token_data.get("token_type", "Bearer"),
        }

        return ToolOAuthCredentials(credentials=new_credentials, expires_at=expires_at)

    def _validate_credentials(self, credentials: dict) -> None:
        """
        Validate the credentials by making a test API call.
        """
        try:
            if "access_token" not in credentials or not credentials.get("access_token"):
                raise ToolProviderCredentialValidationError(
                    "Google Calendar access token is required."
                )

            headers = {
                "Authorization": f"Bearer {credentials['access_token']}",
                "Accept": "application/json",
            }

            # Test API call to verify credentials
            response = requests.get(
                f"{self._API_BASE_URL}/calendars/primary", headers=headers, timeout=10
            )

            if response.status_code == 401:
                raise ToolProviderCredentialValidationError(
                    "Invalid access token or token expired."
                )
            elif response.status_code == 403:
                raise ToolProviderCredentialValidationError(
                    "Insufficient permissions. Please ensure Calendar API access is granted."
                )
            elif response.status_code != 200:
                raise ToolProviderCredentialValidationError(
                    f"API validation failed: {response.text}"
                )

        except requests.Timeout:
            raise ToolProviderCredentialValidationError(
                "Request timeout when validating credentials."
            )
        except requests.RequestException as e:
            raise ToolProviderCredentialValidationError(
                f"Network error during credential validation: {str(e)}"
            )
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Unexpected error during credential validation: {str(e)}"
            )
