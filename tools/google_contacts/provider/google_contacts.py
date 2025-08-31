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


class GoogleContactsProvider(ToolProvider):
    """
    Google Contacts API provider using OAuth 2.0 authentication
    """

    _AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN_URL = "https://oauth2.googleapis.com/token"
    _REVOKE_URL = "https://oauth2.googleapis.com/revoke"
    _USER_INFO_URL = "https://www.googleapis.com/oauth2/v1/userinfo"
    _PEOPLE_API_URL = "https://people.googleapis.com/v1"

    # Built-in scope for Google Contacts - full read/write access
    _CONTACTS_SCOPE = "https://www.googleapis.com/auth/contacts"

    def _oauth_get_authorization_url(
        self, redirect_uri: str, system_credentials: Mapping[str, Any]
    ) -> str:
        """
        Generate the authorization URL for Google OAuth.
        """
        state = secrets.token_urlsafe(16)
        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "scope": self._CONTACTS_SCOPE,  # Use built-in scope
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
        Exchange authorization code for access token.
        """
        code = request.args.get("code")
        if not code:
            raise ToolProviderOAuthError("No authorization code provided")

        # Exchange code for token
        token_data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(
            self._TOKEN_URL, data=token_data, headers=headers, timeout=10
        )

        if response.status_code != 200:
            raise ToolProviderOAuthError(
                f"Failed to exchange code for token: {response.text}"
            )

        token_response = response.json()
        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")
        expires_in = token_response.get("expires_in", 3600)

        if not access_token:
            raise ToolProviderOAuthError(
                f"No access token in response: {token_response}"
            )

        # Calculate expiration timestamp
        import time

        expires_at = int(time.time()) + expires_in

        credentials = {
            "access_token": access_token,
            "refresh_token": refresh_token,
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

        refresh_data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(
            self._TOKEN_URL, data=refresh_data, headers=headers, timeout=10
        )

        if response.status_code != 200:
            raise ToolProviderOAuthError(f"Failed to refresh token: {response.text}")

        token_response = response.json()
        new_access_token = token_response.get("access_token")
        expires_in = token_response.get("expires_in", 3600)

        if not new_access_token:
            raise ToolProviderOAuthError(
                f"No access token in refresh response: {token_response}"
            )

        # Calculate expiration timestamp
        import time

        expires_at = int(time.time()) + expires_in

        # Keep the refresh token if not provided in response
        new_refresh_token = token_response.get("refresh_token", refresh_token)

        new_credentials = {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
        }

        return ToolOAuthCredentials(credentials=new_credentials, expires_at=expires_at)

    def _validate_credentials(self, credentials: dict) -> None:
        """
        Validate the credentials by making a test API call.
        """
        try:
            access_token = credentials.get("access_token")
            if not access_token:
                raise ToolProviderCredentialValidationError("Access token is required")

            # Test the credentials by calling user info endpoint
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }

            response = requests.get(self._USER_INFO_URL, headers=headers, timeout=10)

            if response.status_code == 401:
                raise ToolProviderCredentialValidationError(
                    "Invalid or expired access token"
                )
            elif response.status_code != 200:
                raise ToolProviderCredentialValidationError(
                    f"Failed to validate credentials: {response.text}"
                )

            # Also test access to People API
            people_response = requests.get(
                f"{self._PEOPLE_API_URL}/people/me?personFields=names",
                headers=headers,
                timeout=10,
            )

            if people_response.status_code == 403:
                raise ToolProviderCredentialValidationError(
                    "Insufficient permissions. Please ensure contacts scope is granted."
                )
            elif people_response.status_code != 200:
                raise ToolProviderCredentialValidationError(
                    f"Cannot access Google Contacts API: {people_response.text}"
                )

        except requests.RequestException as e:
            raise ToolProviderCredentialValidationError(
                f"Network error during credential validation: {str(e)}"
            )
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Credential validation failed: {str(e)}"
            )
