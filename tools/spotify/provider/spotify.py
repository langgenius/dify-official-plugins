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


class SpotifyProvider(ToolProvider):
    _AUTH_URL = "https://accounts.spotify.com/authorize"
    _TOKEN_URL = "https://accounts.spotify.com/api/token"
    _API_BASE_URL = "https://api.spotify.com/v1"
    _SCOPES = "user-read-playback-state user-modify-playback-state user-read-currently-playing streaming user-library-read user-library-modify playlist-read-private playlist-modify-public playlist-modify-private user-follow-read user-follow-modify user-top-read user-read-recently-played"

    def _oauth_get_authorization_url(
        self, redirect_uri: str, system_credentials: Mapping[str, Any]
    ) -> str:
        """
        Generate the authorization URL for the Spotify OAuth.
        """
        state = secrets.token_urlsafe(16)
        params = {
            "client_id": system_credentials["client_id"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": self._SCOPES,
            "state": state,
            "show_dialog": "false",
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> ToolOAuthCredentials:
        """
        Exchange authorization code for access token.
        """
        code = request.args.get("code")
        if not code:
            error = request.args.get("error")
            error_description = request.args.get(
                "error_description", "No code provided"
            )
            raise ToolProviderOAuthError(
                f"Authorization failed: {error} - {error_description}"
            )

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            response = requests.post(
                self._TOKEN_URL, data=data, headers=headers, timeout=30
            )
            response.raise_for_status()
            token_data = response.json()

            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 3600)

            if not access_token:
                raise ToolProviderOAuthError("No access token received from Spotify")

            # Calculate expiration timestamp
            import time

            expires_at = int(time.time()) + expires_in

            return ToolOAuthCredentials(
                credentials={
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_in": expires_in,
                },
                expires_at=expires_at,
            )

        except requests.exceptions.RequestException as e:
            raise ToolProviderOAuthError(f"Failed to exchange code for token: {str(e)}")

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
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            response = requests.post(
                self._TOKEN_URL, data=data, headers=headers, timeout=30
            )
            response.raise_for_status()
            token_data = response.json()

            access_token = token_data.get("access_token")
            new_refresh_token = token_data.get(
                "refresh_token", refresh_token
            )  # Keep old if not provided
            expires_in = token_data.get("expires_in", 3600)

            if not access_token:
                raise ToolProviderOAuthError("No access token received during refresh")

            # Calculate expiration timestamp
            import time

            expires_at = int(time.time()) + expires_in

            return ToolOAuthCredentials(
                credentials={
                    "access_token": access_token,
                    "refresh_token": new_refresh_token,
                    "expires_in": expires_in,
                },
                expires_at=expires_at,
            )

        except requests.exceptions.RequestException as e:
            raise ToolProviderOAuthError(f"Failed to refresh token: {str(e)}")

    def _validate_credentials(self, credentials: dict) -> None:
        """
        Validate the credentials by making a test API call.
        """
        try:
            access_token = credentials.get("access_token")
            if not access_token:
                raise ToolProviderCredentialValidationError(
                    "No access token found in credentials"
                )

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            # Test the credentials by fetching the current user's profile
            response = requests.get(
                f"{self._API_BASE_URL}/me", headers=headers, timeout=10
            )

            if response.status_code == 401:
                raise ToolProviderCredentialValidationError(
                    "Invalid or expired access token"
                )
            elif response.status_code != 200:
                error_data = (
                    response.json()
                    if response.headers.get("content-type", "").startswith(
                        "application/json"
                    )
                    else {}
                )
                error_message = error_data.get("error", {}).get(
                    "message", f"API request failed with status {response.status_code}"
                )
                raise ToolProviderCredentialValidationError(
                    f"Spotify API error: {error_message}"
                )

        except requests.exceptions.RequestException as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to validate credentials: {str(e)}"
            )
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Credential validation error: {str(e)}"
            )
