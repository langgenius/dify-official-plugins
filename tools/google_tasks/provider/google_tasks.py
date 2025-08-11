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


class GoogleTasksProvider(ToolProvider):
    _AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN_URL = "https://oauth2.googleapis.com/token"
    _API_BASE_URL = "https://tasks.googleapis.com/tasks/v1"

    # Built-in OAuth scope - only tasks permission needed
    _OAUTH_SCOPES = "https://www.googleapis.com/auth/tasks"

    def _oauth_get_authorization_url(
        self, redirect_uri: str, system_credentials: Mapping[str, Any]
    ) -> str:
        """
        Generate the authorization URL for Google OAuth2.
        """
        state = secrets.token_urlsafe(16)
        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self._OAUTH_SCOPES,  # Use built-in scope
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
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
            raise ToolProviderOAuthError("No authorization code provided")

        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(
            self._TOKEN_URL, data=data, headers=headers, timeout=10
        )

        if response.status_code != 200:
            raise ToolProviderOAuthError(f"Failed to get access token: {response.text}")

        response_json = response.json()
        access_token = response_json.get("access_token")
        refresh_token = response_json.get("refresh_token")
        expires_in = response_json.get("expires_in", 3600)

        if not access_token:
            raise ToolProviderOAuthError(
                f"No access token in response: {response_json}"
            )

        return ToolOAuthCredentials(
            credentials={"access_token": access_token, "refresh_token": refresh_token},
            expires_at=expires_in,
        )

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

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(
            self._TOKEN_URL, data=data, headers=headers, timeout=10
        )

        if response.status_code != 200:
            raise ToolProviderOAuthError(f"Failed to refresh token: {response.text}")

        response_json = response.json()
        access_token = response_json.get("access_token")
        expires_in = response_json.get("expires_in", 3600)

        if not access_token:
            raise ToolProviderOAuthError(
                f"No access token in refresh response: {response_json}"
            )

        return ToolOAuthCredentials(
            credentials={
                "access_token": access_token,
                "refresh_token": refresh_token,  # Keep the original refresh token
            },
            expires_at=expires_in,
        )

    def _validate_credentials(self, credentials: dict) -> None:
        """
        Validate OAuth credentials by attempting to list task lists.
        """
        try:
            if "access_token" not in credentials or not credentials.get("access_token"):
                raise ToolProviderCredentialValidationError(
                    "Google OAuth access token is required."
                )

            headers = {
                "Authorization": f"Bearer {credentials['access_token']}",
                "Accept": "application/json",
            }

            # Test the credentials by attempting to list task lists
            # This is a minimal API call that validates the token has proper Tasks API access
            response = requests.get(
                f"{self._API_BASE_URL}/users/@me/lists",
                headers=headers,
                params={"maxResults": 1},  # Only fetch 1 to minimize data transfer
                timeout=10,
            )

            if response.status_code == 401:
                raise ToolProviderCredentialValidationError(
                    "Invalid or expired access token"
                )
            elif response.status_code == 403:
                raise ToolProviderCredentialValidationError(
                    "Access token does not have Google Tasks API permission"
                )
            elif response.status_code != 200:
                raise ToolProviderCredentialValidationError(
                    f"Failed to validate credentials: {response.text}"
                )

        except requests.RequestException as e:
            raise ToolProviderCredentialValidationError(
                f"Network error while validating credentials: {str(e)}"
            )
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
